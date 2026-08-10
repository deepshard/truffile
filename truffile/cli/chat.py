from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from truffile.client import TruffleClient
from truffile.convo_chat import (
    CompletionFenceLostError,
    ConvoChatSession,
    ConvoLiveEvent,
    ConvoTurnResult,
    ThreadSelectionError,
    history_rows,
)
from truffile.storage import StorageService

from .commands import CHAT_COMMANDS, SlashCommand
from .connect import _resolve_connected_device
from .markdown import count_terminal_lines, has_markdown, render_markdown
from .picker import pick_from_list
from .prompt import TrufflePrompt
from .ui import (
    C,
    CHECK,
    CROSS,
    DOT,
    MUSHROOM,
    ScrollingLog,
    Spinner,
    StreamAbortWatcher,
    create_thinking_orb,
    error,
    info,
    success,
)
from .welcome import show_chat_welcome


APP_RESTRICTION_ERROR = (
    "per-chat app selection is not supported by Convo v1; "
    "use /apps or --list-apps for discovery"
)


def _read_chat_prompt(args) -> str:
    parts: list[str] = []
    prompt_words = getattr(args, "prompt_words", None) or []
    if prompt_words:
        parts.append(" ".join(prompt_words).strip())
    prompt_file = getattr(args, "prompt_file", None)
    if prompt_file:
        path = Path(prompt_file).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"--prompt-file not found: {path}")
        parts.append(path.read_text(encoding="utf-8").strip())
    use_stdin = bool(getattr(args, "stdin", False)) or (
        not sys.stdin.isatty() and not prompt_words and not prompt_file
    )
    if use_stdin:
        try:
            data = sys.stdin.read()
        except Exception:
            data = ""
        if data:
            parts.append(data.strip())
    return "\n\n".join(part for part in parts if part)


def _is_oneshot_chat(args) -> bool:
    one_shot_values = (
        getattr(args, "list_apps", False),
        getattr(args, "list_threads", None) is not None,
        getattr(args, "prompt_file", None),
        getattr(args, "stdin", False),
        getattr(args, "thread_id", None),
        getattr(args, "thread", None),
        getattr(args, "resume_last", False),
        getattr(args, "new", False),
        getattr(args, "rename", None),
        getattr(args, "history", False),
        getattr(args, "interrupt", False),
        getattr(args, "hide", None),
        getattr(args, "restore", None),
        getattr(args, "prompt_words", None),
    )
    if any(one_shot_values):
        return True
    if getattr(args, "main", False) and getattr(args, "prompt_words", None):
        return True
    return not sys.stdin.isatty()


def _eprint_factory(quiet: bool):
    if quiet:
        return lambda _message: None

    def emit(message: str) -> None:
        sys.stderr.write(message + "\n")
        sys.stderr.flush()

    return emit


async def _get_apps_list(client: TruffleClient) -> list[dict[str, str]]:
    apps = await client.get_all_apps()
    result = []
    for app in apps:
        metadata = app.metadata
        result.append(
            {
                "name": metadata.name if hasattr(metadata, "name") else "?",
                "bundle_id": metadata.bundle_id if hasattr(metadata, "bundle_id") else "",
                "uuid": app.uuid,
            }
        )
    return result


def _find_app_by_name(apps: list[dict[str, str]], name: str) -> dict[str, str] | None:
    wanted = name.strip().casefold()
    for app in apps:
        app_name = app.get("name", "").casefold()
        if app_name == wanted or wanted in app_name:
            return app
    return None


async def _connect_client(storage: StorageService, *, quiet: bool) -> tuple[str, TruffleClient] | None:
    eprint = _eprint_factory(quiet)
    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return None
    token = storage.get_token(device)
    if not token:
        eprint(f"no token for {device}")
        return None
    client = TruffleClient(
        f"{ip}:80", token=token, app_id=storage.app_id_for_device(device)
    )
    try:
        await client.connect()
        if not await client.check_auth():
            raise RuntimeError("stored device session is no longer authenticated")
    except Exception as exc:
        eprint(f"could not connect to {device}: {exc}")
        await client.close()
        return None
    return device, client


async def _start_session(
    client: TruffleClient, storage: StorageService, device: str
) -> tuple[ConvoChatSession, str]:
    identity = await client.get_current_user_identity()
    user_id = str(getattr(identity, "user_id", "") or "").strip()
    if not user_id:
        raise RuntimeError("the authenticated session did not resolve to a user id")
    hidden = storage.hidden_convo_thread_ids(device, user_id)
    session = ConvoChatSession(client, hidden_thread_ids=hidden)
    await session.start()
    return session, user_id


def _result_payload(result: ConvoTurnResult, device: str) -> dict[str, Any]:
    thread_id = str(result.thread_id)
    return {
        "task_id": thread_id,
        "thread_id": thread_id,
        "backend": "convo",
        "title": result.title,
        "device": device,
        "content": result.content,
        "thinking": result.thinking or None,
        "tool_calls": result.tool_calls or None,
        "pending_user_response": result.pending_user_response,
        "attached_apps": None,
        "status": result.status,
        "error": result.error,
        "interrupted": result.interrupted,
        "timed_out": result.timed_out,
    }


def _emit_failure(
    message: str,
    *,
    json_output: bool,
    device: str = "",
    status: str = "error",
    quiet: bool = False,
) -> None:
    if json_output:
        print(
            json.dumps(
                {
                    "backend": "convo",
                    "device": device or None,
                    "status": status,
                    "error": message,
                },
                ensure_ascii=False,
            )
        )
    elif not quiet:
        sys.stderr.write(f"error: {message}\n")


def _print_thread_rows(rows: list[dict[str, Any]], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps({"threads": rows, "tasks": rows, "backend": "convo"}, indent=2))
        return
    for row in rows:
        hidden = "\thidden-local" if row["hidden_local"] else ""
        print(
            f"{row['thread_id']}\t{row['updated'][:16]}\t{row['title']}"
            f"\t{row['thread_kind']}{hidden}"
        )


def _print_history(nodes: list[Any], *, json_output: bool = False) -> None:
    rows = history_rows(nodes)
    if json_output:
        print(json.dumps({"history": rows, "backend": "convo"}, indent=2, ensure_ascii=False))
        return
    if not rows:
        print("(no history)")
        return
    labels = {
        "user": "you",
        "ai": "agent",
        "error": "error",
        "system": "system",
        "forward": "forward",
        "setup": "setup",
        "action": "action",
    }
    for row in rows:
        label = labels.get(row["kind"], row["kind"])
        print(f"{C.DIM}{label}>{C.RESET} {row['content']}")
        for tool in row["tool_calls"]:
            print(f"  {C.CYAN}{DOT} tool: {tool}{C.RESET}")


async def _select_target(session: ConvoChatSession, args) -> bool:
    if getattr(args, "main", False):
        await session.select_thread(0)
        return True
    raw_thread_id = getattr(args, "thread_id", None)
    if raw_thread_id is not None:
        raw = str(raw_thread_id).strip()
        if not raw.lstrip("-").isdigit():
            raise ThreadSelectionError(
                "legacy Task chats are not available after the Convo cutover; "
                "--thread-id/--task-id requires a decimal Convo thread id"
            )
        await session.select_thread(
            session.resolve_thread(raw, include_hidden=getattr(args, "include_hidden", False)),
            include_hidden=getattr(args, "include_hidden", False),
        )
        return True
    selector = getattr(args, "thread", None)
    if selector:
        thread_id = session.resolve_thread(
            selector, include_hidden=getattr(args, "include_hidden", False)
        )
        await session.select_thread(
            thread_id, include_hidden=getattr(args, "include_hidden", False)
        )
        return True
    if getattr(args, "resume_last", False):
        await session.select_thread(
            session.latest_thread_id(include_hidden=getattr(args, "include_hidden", False)),
            include_hidden=getattr(args, "include_hidden", False),
        )
        return True
    session.new_thread()
    return False


async def _run_oneshot_chat(args, storage: StorageService) -> int:
    quiet = bool(getattr(args, "quiet", False))
    json_output = bool(getattr(args, "json", False))
    if getattr(args, "app", None):
        _emit_failure(APP_RESTRICTION_ERROR, json_output=json_output, quiet=quiet)
        return 2

    connected = await _connect_client(storage, quiet=quiet)
    if connected is None:
        return 1
    device, client = connected
    session: ConvoChatSession | None = None
    try:
        if getattr(args, "list_apps", False):
            apps = await _get_apps_list(client)
            if json_output:
                print(json.dumps({"apps": apps}, indent=2))
            else:
                for app in apps:
                    slug = app["name"].lower().replace(" ", "-")
                    print(f"{slug}\t{app['name']}\t{app['uuid']}")
            return 0

        try:
            session, user_id = await _start_session(client, storage, device)
        except Exception as exc:
            _emit_failure(str(exc), json_output=json_output, device=device, quiet=quiet)
            return 1

        try:
            prompt_text = _read_chat_prompt(args)
        except FileNotFoundError as exc:
            _emit_failure(str(exc), json_output=json_output, device=device, quiet=quiet)
            return 2

        include_hidden = bool(getattr(args, "include_hidden", False))
        restore_selector = getattr(args, "restore", None)
        if restore_selector:
            thread_id = session.resolve_thread(restore_selector, include_hidden=True)
            storage.restore_convo_thread(device, user_id, thread_id)
            session.restore_thread(thread_id)
            if json_output:
                print(json.dumps({"thread_id": str(thread_id), "restored_local": True}))
            elif not quiet:
                print(f"restored Convo thread {thread_id} to this machine's list")
            return 0

        hide_selector = getattr(args, "hide", None)
        if hide_selector:
            thread_id = session.resolve_thread(hide_selector, include_hidden=include_hidden)
            storage.hide_convo_thread(device, user_id, thread_id)
            session.hide_thread(thread_id)
            if json_output:
                print(json.dumps({"thread_id": str(thread_id), "hidden_local": True}))
            elif not quiet:
                print(
                    f"Convo thread {thread_id} hidden on this machine; "
                    "it was not deleted from Convo"
                )
            return 0

        if getattr(args, "list_threads", None) is not None:
            limit = int(getattr(args, "list_threads") or 15)
            if limit <= 0:
                _emit_failure(
                    "thread list size must be greater than zero",
                    json_output=json_output,
                    device=device,
                    quiet=quiet,
                )
                return 2
            rows = session.thread_rows(include_hidden=include_hidden)[:limit]
            _print_thread_rows(rows, json_output=json_output)
            return 0

        selected_existing = await _select_target(session, args)

        if getattr(args, "history", False):
            if session.selected_thread_id is None:
                _emit_failure(
                    "--history requires --thread, --thread-id, --main, or --resume-last",
                    json_output=json_output,
                    device=device,
                    quiet=quiet,
                )
                return 2
            _print_history(
                session.reducer.thread_nodes(session.selected_thread_id),
                json_output=json_output,
            )
            if not prompt_text and not getattr(args, "rename", None):
                return 0

        if getattr(args, "interrupt", False):
            if session.selected_thread_id is None:
                _emit_failure(
                    "--interrupt requires --thread, --thread-id, --main, or --resume-last",
                    json_output=json_output,
                    device=device,
                    quiet=quiet,
                )
                return 2
            await session.request_interrupt()
            if json_output:
                print(json.dumps({"thread_id": str(session.selected_thread_id), "interrupted": True}))
            elif not quiet:
                print(f"interrupt requested for Convo thread {session.selected_thread_id}")
            return 0

        rename = getattr(args, "rename", None)
        if rename and not prompt_text:
            if session.selected_thread_id is None:
                _emit_failure(
                    "renaming a new thread requires a prompt so Convo can create it",
                    json_output=json_output,
                    device=device,
                    quiet=quiet,
                )
                return 2
            await session.rename_selected(rename)
            if json_output:
                print(
                    json.dumps(
                        {
                            "thread_id": str(session.selected_thread_id),
                            "title": rename,
                            "backend": "convo",
                        }
                    )
                )
            elif not quiet:
                print(f'renamed Convo thread {session.selected_thread_id} to "{rename}"')
            return 0

        if not prompt_text:
            if selected_existing and session.selected_thread_id is not None:
                result = session.latest_result(session.selected_thread_id)
            else:
                _emit_failure(
                    "no prompt provided (positional, --prompt-file, or --stdin required)",
                    json_output=json_output,
                    device=device,
                    quiet=quiet,
                )
                return 2
        else:
            try:
                result = await session.send(
                    prompt_text, timeout=getattr(args, "timeout", None)
                )
            except CompletionFenceLostError as exc:
                partial = (
                    session.latest_result(session.selected_thread_id)
                    if session.selected_thread_id is not None
                    else None
                )
                if json_output and partial is not None:
                    payload = _result_payload(partial, device)
                    payload.update({"status": "fence_lost", "error": str(exc)})
                    print(json.dumps(payload, indent=2, ensure_ascii=False))
                else:
                    _emit_failure(str(exc), json_output=json_output, device=device, quiet=quiet)
                return 75
            if rename:
                await session.rename_selected(rename)
                result.title = rename

        if json_output:
            print(json.dumps(_result_payload(result, device), indent=2, ensure_ascii=False))
        else:
            if getattr(args, "show_thinking", False) and result.thinking:
                sys.stderr.write("--- thinking ---\n")
                sys.stderr.write(" ".join(result.thinking) + "\n")
                sys.stderr.write("--- end thinking ---\n")
            if result.content:
                print(result.content)
            if result.error and not result.content:
                sys.stderr.write(f"error: {result.error}\n")

        if result.timed_out:
            return 124
        if result.status == "error":
            return 1
        if result.status == "interaction_required":
            return 3
        if result.interrupted:
            return 130
        return 0
    except (ThreadSelectionError, ValueError) as exc:
        _emit_failure(str(exc), json_output=json_output, device=device, quiet=quiet)
        return 2
    except Exception as exc:
        _emit_failure(str(exc), json_output=json_output, device=device, quiet=quiet)
        return 1
    finally:
        if session is not None:
            await session.close()
        await client.close()


async def _pick_thread(
    session: ConvoChatSession,
    *,
    current_thread_id: int | None = None,
    include_hidden: bool = False,
    hidden_only: bool = False,
) -> int | None:
    rows = session.thread_rows(include_hidden=include_hidden)
    if hidden_only:
        rows = [row for row in rows if row["hidden_local"]]
    if not rows:
        info("no matching Convo threads found")
        return None
    items = [
        {
            "label": row["title"],
            "detail": f"{row['updated'][:16]} · {row['thread_id']}",
            "thread_id": int(row["thread_id"]),
        }
        for row in rows
    ]
    print()
    picked = await pick_from_list(
        items,
        label_key="label",
        detail_key="detail",
        active_key="thread_id" if current_thread_id is not None else None,
        active_value=current_thread_id,
        prompt="pick a conversation",
    )
    return int(picked["thread_id"]) if picked else None


def _maybe_render_markdown(text: str) -> None:
    if not text or not has_markdown(text):
        return
    try:
        width = shutil.get_terminal_size().columns
        render_markdown(text, count_terminal_lines(text, width))
    except Exception:
        pass


def _confirm_local_hide(title: str) -> bool:
    try:
        answer = input(
            f'Hide "{title}" on this machine? It will not be deleted from Convo. [y/N] '
        )
    except (EOFError, KeyboardInterrupt):
        return False
    return answer.strip().casefold() in {"y", "yes"}


async def _send_interactive(session: ConvoChatSession, text: str) -> ConvoTurnResult:
    orb = create_thinking_orb()
    orb.start(orb.STATE_ACTIVE)
    orb_stopped = False
    streamed: list[str] = []

    async def live(event: ConvoLiveEvent) -> None:
        nonlocal orb_stopped
        if not orb_stopped and event.kind in {"reply", "tool", "error"}:
            orb.stop()
            orb_stopped = True
        if event.kind == "reply":
            streamed.append(event.content)
            sys.stdout.write(event.content)
            sys.stdout.flush()
        elif event.kind == "tool":
            print(f"\n{C.CYAN}{DOT} tool: {event.content}{C.RESET}")
        elif event.kind == "error":
            print(f"\n{C.RED}error: {event.content}{C.RESET}")

    task = asyncio.create_task(session.send(text, on_live_event=live))
    interrupt_sent = False
    with StreamAbortWatcher() as watcher:
        while not task.done():
            await asyncio.wait({task}, timeout=0.05)
            if watcher.aborted() and not interrupt_sent:
                interrupt_sent = True
                print(f"\n{C.DIM}interrupting Convo thread...{C.RESET}")
                await session.request_interrupt()
    if not orb_stopped:
        orb.stop()
    result = await task
    streamed_text = "".join(streamed)
    if streamed_text:
        print()
        _maybe_render_markdown(streamed_text)
    elif result.content:
        print(result.content)
        _maybe_render_markdown(result.content)
    if result.thinking:
        print(f"{C.GRAY}thinking: {' '.join(result.thinking)}{C.RESET}")
    if result.error:
        print(f"{C.RED}error: {result.error}{C.RESET}")
    return result


async def _interactive_delete_app(
    arg: str, client: TruffleClient
) -> bool:
    app_name = arg[4:].strip() if len(arg) > 4 else ""
    apps = await _get_apps_list(client)
    if not apps:
        info("no apps installed")
        return False
    if app_name:
        match = _find_app_by_name(apps, app_name)
        if not match:
            error(f'app "{app_name}" not found')
            return False
    else:
        items = [
            {"label": app["name"], "detail": app["bundle_id"], "uuid": app["uuid"]}
            for app in apps
        ]
        picked = await pick_from_list(
            items, label_key="label", detail_key="detail", prompt="pick app to delete"
        )
        if not picked:
            return False
        match = {"name": picked["label"], "uuid": picked["uuid"]}
    await client.delete_app(match["uuid"])
    success(f"deleted {match['name']}")
    return True


async def _interactive_deploy(arg: str, client: TruffleClient, storage: StorageService) -> bool:
    if not arg:
        error("usage: /deploy <path>")
        return False
    app_dir = Path(arg).resolve()
    if not app_dir.exists():
        error(f"path not found: {arg}")
        return False
    from truffile.deploy import deploy_with_builder
    from truffile.schema import validate_app_dir
    from .deploy import _interactive_shell

    valid, config, app_type, _warnings, errors_list = validate_app_dir(app_dir)
    if not valid:
        for message in errors_list:
            error(message)
        return False
    result = await deploy_with_builder(
        client=client,
        config=config,
        app_dir=app_dir,
        app_type=app_type,
        device=storage.state.last_used_device or "device",
        interactive=False,
        spinner_cls=Spinner,
        scrolling_log_cls=ScrollingLog,
        info=info,
        success=success,
        error=error,
        color_dim=C.DIM,
        color_reset=C.RESET,
        color_bold=C.BOLD,
        arrow="→",
        interactive_shell=_interactive_shell,
    )
    return result == 0


async def _run_interactive_chat(args, storage: StorageService) -> int:
    connected = await _connect_client(storage, quiet=False)
    if connected is None:
        return 1
    device, client = connected
    session: ConvoChatSession | None = None
    spinner = Spinner(f"Opening Convo on {device}")
    spinner.start()
    try:
        try:
            session, user_id = await _start_session(client, storage, device)
            spinner.stop(success=True)
        except Exception as exc:
            spinner.fail(f"Could not open Convo on {device}")
            error(str(exc))
            return 1

        if getattr(args, "main", False):
            await session.select_thread(0)
        elif getattr(args, "resume", False):
            picked = await _pick_thread(session)
            if picked is not None:
                nodes = await session.select_thread(picked)
                _print_history(nodes)

        try:
            apps = await _get_apps_list(client)
        except Exception:
            apps = []
        app_commands = {
            f"/{app['name'].lower().replace(' ', '-')}": app for app in apps
        }
        prompt = TrufflePrompt("you> ", CHAT_COMMANDS)
        if app_commands:
            prompt.add_commands(
                [
                    SlashCommand(command, "unsupported in Convo v1")
                    for command in sorted(app_commands)
                ]
            )
        prompt.task_name = (
            session.reducer.title_for_thread(session.selected_thread_id)
            if session.selected_thread_id is not None
            else "New thread"
        )
        show_chat_welcome(
            device=device,
            apps=[command.removeprefix("/") for command in app_commands] or None,
        )

        while True:
            user_input = await prompt.get_input()
            if user_input is None:
                print()
                break
            stripped = user_input.strip()
            if not stripped:
                continue
            if stripped.startswith("/"):
                parts = stripped.split(maxsplit=1)
                command = parts[0].casefold()
                arg = parts[1].strip() if len(parts) > 1 else ""

                if command in app_commands:
                    error(APP_RESTRICTION_ERROR)
                    continue
                if command == "/help":
                    print(f"\n{C.BOLD}commands:{C.RESET}")
                    for slash in CHAT_COMMANDS:
                        display = f"{slash.name} {slash.arg_hint}" if slash.arg_hint else slash.name
                        print(f"  {C.CYAN}{display}{C.RESET} — {slash.description}")
                    print()
                    continue
                if command in {"/exit", "/quit"}:
                    break
                if command == "/new":
                    session.new_thread()
                    prompt.task_name = "New thread"
                    info("the next message will create a new side thread")
                    continue
                if command == "/main":
                    nodes = await session.select_thread(0)
                    prompt.task_name = session.reducer.title_for_thread(0)
                    _print_history(nodes)
                    continue
                if command in {"/threads", "/chats", "/tasks", "/resume", "/switch"}:
                    picked = await _pick_thread(
                        session, current_thread_id=session.selected_thread_id
                    )
                    if picked is not None:
                        nodes = await session.select_thread(picked)
                        prompt.task_name = session.reducer.title_for_thread(picked)
                        _print_history(nodes)
                    continue
                if command == "/history":
                    if session.selected_thread_id is None:
                        info("new thread has no history yet")
                    else:
                        _print_history(session.reducer.thread_nodes(session.selected_thread_id))
                    continue
                if command == "/title":
                    if session.selected_thread_id is None:
                        print("  New thread (unsent)")
                    else:
                        print(f"  {session.reducer.title_for_thread(session.selected_thread_id)}")
                    continue
                if command == "/rename":
                    if not arg:
                        error("usage: /rename <name>")
                        continue
                    try:
                        await session.rename_selected(arg)
                        prompt.task_name = arg
                        success(f'renamed to "{arg}"')
                    except Exception as exc:
                        error(str(exc))
                    continue
                if command == "/interrupt":
                    try:
                        await session.request_interrupt()
                        success("interrupt requested")
                    except Exception as exc:
                        error(str(exc))
                    continue
                if command in {"/hide", "/delete"}:
                    if command == "/delete" and not arg.casefold().startswith("task"):
                        if arg.casefold().startswith("app"):
                            try:
                                await _interactive_delete_app(arg, client)
                                apps = await _get_apps_list(client)
                            except Exception as exc:
                                error(str(exc))
                        else:
                            error("usage: /delete app [name] or /delete task")
                        continue
                    thread_id = session.selected_thread_id
                    selector = ""
                    if command == "/delete" and arg.casefold().startswith("task"):
                        selector = arg[4:].strip()
                        if not selector:
                            thread_id = await _pick_thread(
                                session, current_thread_id=session.selected_thread_id
                            )
                    elif arg and arg.casefold() not in {"current", "thread"}:
                        selector = arg
                    if selector:
                        try:
                            thread_id = session.resolve_thread(selector)
                        except Exception as exc:
                            error(str(exc))
                            continue
                    if thread_id is None:
                        error("no active thread")
                        continue
                    title = session.reducer.title_for_thread(thread_id)
                    if _confirm_local_hide(title):
                        try:
                            storage.hide_convo_thread(device, user_id, thread_id)
                            session.hide_thread(thread_id)
                            prompt.task_name = "New thread"
                            success("hidden on this machine; not deleted from Convo")
                        except Exception as exc:
                            error(str(exc))
                    continue
                if command == "/restore":
                    try:
                        thread_id = (
                            session.resolve_thread(arg, include_hidden=True)
                            if arg
                            else await _pick_thread(
                                session, include_hidden=True, hidden_only=True
                            )
                        )
                        if thread_id is not None:
                            storage.restore_convo_thread(device, user_id, thread_id)
                            session.restore_thread(thread_id)
                            success("restored to this machine's conversation list")
                    except Exception as exc:
                        error(str(exc))
                    continue
                if command == "/deploy":
                    try:
                        if await _interactive_deploy(arg, client, storage):
                            success("deploy complete")
                    except Exception as exc:
                        error(f"deploy failed: {exc}")
                    continue
                if command == "/devices":
                    for stored_device in storage.list_devices():
                        marker = " (active)" if stored_device == device else ""
                        print(f"  {stored_device}{marker}")
                    continue
                if command == "/create":
                    from .create import cmd_create

                    cmd_create(SimpleNamespace(name=arg or None, path=None))
                    continue
                error(f"unknown command: {command}. type /help")
                continue

            print()
            try:
                await _send_interactive(session, stripped)
            except CompletionFenceLostError as exc:
                error(str(exc))
            except Exception as exc:
                error(str(exc))
            prompt.task_name = (
                session.reducer.title_for_thread(session.selected_thread_id)
                if session.selected_thread_id is not None
                else "New thread"
            )
            print()
        return 0
    except KeyboardInterrupt:
        if session is not None and session.selected_thread_id is not None:
            try:
                await session.request_interrupt()
            except Exception:
                pass
        return 130
    finally:
        if session is not None:
            await session.close()
        await client.close()
        print(f"\n{MUSHROOM} goodbye!")


async def cmd_convo(args, storage: StorageService) -> int:
    if _is_oneshot_chat(args):
        return await _run_oneshot_chat(args, storage)
    return await _run_interactive_chat(args, storage)


# One-release internal import compatibility; the public command is `convo`.
cmd_chat = cmd_convo
