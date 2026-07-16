from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from truffile.storage import StorageService
from truffile.client import TruffleClient, resolve_mdns
from .ui import C, MUSHROOM, DOT, CHECK, CROSS, Spinner, ScrollingLog, StreamAbortWatcher, error, success, info, warn, create_thinking_orb
from .connect import _resolve_connected_device
from .output import emit_error, emit_json, ok_payload, truncate_text
from .picker import pick_from_list
from .commands import CHAT_COMMANDS, SlashCommand
from .prompt import TrufflePrompt
from .markdown import has_markdown, render_markdown, count_terminal_lines
from .art import ParticleOrb
from .welcome import show_chat_welcome


@dataclass
class TaskState:
    task_id: str = ""
    title: str = ""
    run_state: str = ""
    error_message: str = ""
    pending_node_id: int | None = None
    pending_source_node_id: int | None = None
    result_text: str = ""
    tool_calls: list[str] = field(default_factory=list)
    thinking_summaries: list[str] = field(default_factory=list)


# accumulated streaming text for markdown re-render
_streaming_text: list[str] = []


def _print_update(update: Any, state: TaskState, *, quiet: bool = False) -> None:
    if update.task_id and not state.task_id:
        state.task_id = update.task_id

    if update.HasField("info"):
        run_state = update.info.TaskRunState.Name(update.info.run_state) if update.info.run_state else ""
        if run_state:
            state.run_state = run_state
        title = update.info.task_title
        if title:
            state.title = title

    if update.HasField("error"):
        msg = update.error.message if hasattr(update.error, "message") else str(update.error)
        state.error_message = msg
        if not quiet:
            print(f"\n{C.RED}error: {msg}{C.RESET}")

    # render thinking/tools BEFORE streaming content so they appear above the response
    for node in sorted(update.nodes, key=lambda item: getattr(item, "id", 0)):
        node_id = int(getattr(node, "id", 0) or 0)
        if (
            node.HasField("user_msg")
            and state.pending_source_node_id is not None
            and node_id > state.pending_source_node_id
        ):
            state.pending_node_id = None
            state.pending_source_node_id = None
        if not node.HasField("step"):
            continue

        step = node.step

        if step.HasField("thinking"):
            for s in step.thinking.cot_summaries:
                state.thinking_summaries.append(s)

        for tc in step.tool_calls:
            name = tc.tool_name if hasattr(tc, "tool_name") else ""
            tc_summary = tc.summary if hasattr(tc, "summary") else ""
            if name:
                if not quiet:
                    print(f"{C.CYAN}{DOT} tool: {name}{C.RESET}", end="")
                    if tc_summary:
                        print(f" {C.DIM}— {tc_summary}{C.RESET}")
                    else:
                        print()
                state.tool_calls.append(name)

        if step.HasField("results"):
            content = step.results.content if hasattr(step.results, "content") else ""
            res_summary = step.results.summary if hasattr(step.results, "summary") else ""
            text = content or res_summary
            if text:
                state.result_text = text

        if (
            step.HasField("user_response")
            and step.user_response.node_id
            and step.StepState.Name(step.state) != "STEP_RESULT"
        ):
            node_id = step.user_response.node_id if hasattr(step.user_response, "node_id") else 0
            if node_id:
                state.pending_node_id = node_id
                state.pending_source_node_id = int(getattr(node, "id", 0) or 0)

    # stream content after thinking/tools are rendered
    if update.HasField("streaming_step_result"):
        chunk = update.streaming_step_result.partial_content
        if chunk:
            if not quiet:
                sys.stdout.write(chunk)
                sys.stdout.flush()
            _streaming_text.append(chunk)


async def _stream_task(
    client: TruffleClient,
    stream: Any,
    state: TaskState,
    orb: ParticleOrb | None = None,
    *,
    quiet: bool = False,
    timeout: float | None = None,
) -> bool:
    global _streaming_text
    _streaming_text = []
    interrupted = False
    timed_out = False
    orb_stopped = False

    if orb and not quiet:
        orb.start(ParticleOrb.STATE_ACTIVE)

    abort_cm: Any = StreamAbortWatcher() if not quiet else _NullAbort()
    with abort_cm as abort:
        async def consume() -> None:
            nonlocal interrupted, orb_stopped
            async for update in stream:
                if abort.aborted():
                    interrupted = True
                    break
                # stop orb only when actual visible content arrives
                if orb and not orb_stopped and not quiet:
                    has_content = (
                        update.HasField("streaming_step_result")
                        and update.streaming_step_result.partial_content
                    )
                    if has_content:
                        orb.stop()
                        orb_stopped = True
                _print_update(update, state, quiet=quiet)
                if state.pending_node_id is not None:
                    break

        try:
            if timeout is not None:
                await asyncio.wait_for(consume(), timeout=max(0.1, timeout))
            else:
                await consume()
        except asyncio.TimeoutError:
            interrupted = True
            timed_out = True
        except (asyncio.CancelledError, KeyboardInterrupt):
            interrupted = True
        except Exception as exc:
            interrupted = True
            state.error_message = str(exc)

    if orb and not orb_stopped and not quiet:
        orb.stop()

    if interrupted and state.task_id:
        if not quiet:
            print(f"\n{C.DIM}interrupting...{C.RESET}")
        try:
            await client.interrupt_task(state.task_id)
        except Exception:
            pass
    return timed_out


class _NullAbort:
    """Drop-in replacement for StreamAbortWatcher in quiet mode (no TTY required)."""
    def __enter__(self) -> "_NullAbort":
        return self
    def __exit__(self, *args) -> None:
        return None
    def aborted(self) -> bool:
        return False


async def _pick_task(client: TruffleClient, *, current_task_id: str = "") -> str | None:
    tasks = await client.get_task_infos(max_before=15)
    if not tasks:
        info("no previous tasks found")
        return None

    items = [
        {
            "label": t["title"],
            "detail": t["updated"][:16] if t["updated"] else "",
            "task_id": t["task_id"],
        }
        for t in tasks
    ]

    print()
    picked = await pick_from_list(
        items,
        label_key="label",
        detail_key="detail",
        active_key="task_id" if current_task_id else None,
        active_value=current_task_id,
        prompt="pick a task",
    )
    return picked["task_id"] if picked else None


async def _get_apps_list(client: TruffleClient) -> list[dict]:
    apps = await client.get_all_apps()
    result = []
    for app in apps:
        meta = app.metadata
        name = meta.name if hasattr(meta, "name") else "?"
        bundle_id = meta.bundle_id if hasattr(meta, "bundle_id") else ""
        result.append({"name": name, "bundle_id": bundle_id, "uuid": app.uuid})
    return result


def _find_app_by_name(apps: list, name: str) -> dict | None:
    name_lower = name.strip().lower()
    for app in apps:
        app_name = app.get("name", "").lower()
        if app_name == name_lower or name_lower in app_name:
            return app
    return None


async def _refresh_app_commands(
    client: TruffleClient,
    app_commands: dict[str, dict],
    prompt: "TrufflePrompt | None" = None,
) -> list[str]:
    """Reload installed apps from the device and update app_commands in place.

    Also appends any newly-discovered slugs to the prompt's slash-command
    completer if a prompt is given. Returns the list of slugs (for display).
    """
    try:
        apps_list = await _get_apps_list(client)
    except Exception:
        return []

    app_commands.clear()
    slugs: list[str] = []
    for a in apps_list:
        slug = a["name"].lower().replace(" ", "-")
        app_commands[f"/{slug}"] = a
        slugs.append(slug)

    if prompt is not None and slugs:
        prompt.add_commands([
            SlashCommand(f"/{s}", f"add {app_commands[f'/{s}']['name']} to task")
            for s in slugs
        ])
    return slugs


async def _handle_slash(
    cmd: str,
    client: TruffleClient,
    state: TaskState,
    storage: StorageService,
    *,
    app_commands: dict[str, dict] | None = None,
) -> str | None:
    """returns action string or None. 'exit' to quit, 'new' for fresh task, 'switch:<id>' to resume."""

    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    # check if this is a /<appname> shortcut
    if app_commands and command in app_commands:
        app = app_commands[command]
        if not state.task_id:
            error("no active task — send a message first")
            return None
        try:
            await client.set_task_apps(state.task_id, [app["uuid"]])
            success(f"added {app['name']} to task")
        except Exception as e:
            error(f"failed: {e}")
        return None

    if command == "/help":
        print(f"\n{C.BOLD}commands:{C.RESET}")
        for sc in CHAT_COMMANDS:
            display = f"{sc.name} {sc.arg_hint}" if sc.arg_hint else sc.name
            print(f"  {C.CYAN}{display}{C.RESET} — {sc.description}")
        print(f"\n{C.DIM}alt+enter for newline · tab to complete commands · ctrl+d to exit{C.RESET}\n")
        return None

    if command in ("/exit", "/quit"):
        return "exit"

    if command == "/title":
        print(f"  {state.title or 'no title yet'}")
        return None

    if command == "/rename":
        if not arg:
            error("usage: /rename <new name>")
            return None
        if not state.task_id:
            error("no active task")
            return None
        try:
            await client.rename_task(state.task_id, arg)
            state.title = arg
            success(f"renamed to \"{arg}\"")
        except Exception as e:
            error(f"rename failed: {e}")
        return None

    if command in ("/tasks", "/resume", "/switch"):
        task_id = await _pick_task(client, current_task_id=state.task_id)
        return f"switch:{task_id}" if task_id else None

    if command == "/new":
        return "new"

    if command == "/apps":
        try:
            apps_list = await _get_apps_list(client)
            if not apps_list:
                info("no apps installed")
                return None
            print(f"\n{C.BOLD}installed apps:{C.RESET}")
            for a in apps_list:
                slug = a["name"].lower().replace(" ", "-")
                print(f"  {C.CYAN}/{slug}{C.RESET}  {a['name']} {C.DIM}({a['bundle_id']}){C.RESET}")
            print()
        except Exception as e:
            error(f"failed to list apps: {e}")
        return None

    if command == "/delete":
        if not arg:
            error("usage: /delete app [name] or /delete task")
            return None

        if arg.lower().strip() == "task" or arg.lower().startswith("task "):
            task_to_delete = await _pick_task(client, current_task_id=state.task_id)
            if not task_to_delete:
                return None
            try:
                await client.delete_task(task_to_delete)
                success("task deleted")
                if task_to_delete == state.task_id:
                    return "new"
            except Exception as e:
                error(f"failed: {e}")
            return None

        if arg.lower().strip() == "app" or arg.lower().startswith("app "):
            app_name = arg[4:].strip() if len(arg) > 4 else ""
            try:
                apps_list = await _get_apps_list(client)
                if not apps_list:
                    info("no apps installed")
                    return None

                if not app_name:
                    items = [{"label": a["name"], "detail": a["bundle_id"], "uuid": a["uuid"]} for a in apps_list]
                    print()
                    picked = await pick_from_list(items, label_key="label", detail_key="detail", prompt="pick app to delete")
                    if not picked:
                        return None
                    match = {"name": picked["label"], "uuid": picked["uuid"]}
                else:
                    match = _find_app_by_name(apps_list, app_name)
                    if not match:
                        error(f"app \"{app_name}\" not found")
                        return None

                await client.delete_app(match["uuid"])
                success(f"deleted {match['name']}")
                return "refresh_apps"
            except Exception as e:
                error(f"failed: {e}")
            return None

        error("usage: /delete app [name] or /delete task")
        return None

    if command == "/deploy":
        if not arg:
            error("usage: /deploy <path>")
            return None
        app_dir = Path(arg).resolve()
        if not app_dir.exists():
            error(f"path not found: {arg}")
            return None
        try:
            from truffile.schema import validate_app_dir
            from truffile.deploy import build_deploy_plan, deploy_with_builder
            from .deploy import _interactive_shell

            valid, config, app_type, warnings, errors_list = validate_app_dir(app_dir)
            if not valid:
                for msg in errors_list:
                    error(msg)
                return None

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
            if result == 0:
                success("deploy complete")
                return "refresh_apps"
        except Exception as e:
            error(f"deploy failed: {e}")
        return None

    if command == "/devices":
        devices = storage.list_devices()
        if not devices:
            info("no devices connected")
            return None
        current = storage.state.last_used_device
        print()
        for d in devices:
            marker = f" {C.GREEN}(active){C.RESET}" if d == current else ""
            print(f"  {C.CYAN}{DOT}{C.RESET} {d}{marker}")
        print()
        return None

    if command == "/create":
        from .create import cmd_create
        from types import SimpleNamespace
        create_args = SimpleNamespace(name=arg or None, path=None)
        cmd_create(create_args)
        return None

    error(f"unknown command: {command}. type /help")
    return None


def _maybe_render_markdown(text: str) -> None:
    """If text has markdown, re-render with rich."""
    if not text or not has_markdown(text):
        return
    try:
        width = shutil.get_terminal_size().columns
        lines = count_terminal_lines(text, width)
        render_markdown(text, lines)
    except Exception:
        pass


def _is_oneshot_chat(args) -> bool:
    if getattr(args, "list_apps", False):
        return True
    if getattr(args, "list_tasks", None) is not None:
        return True
    if getattr(args, "prompt_file", None):
        return True
    if getattr(args, "stdin", False):
        return True
    if getattr(args, "task_id", None):
        return True
    if getattr(args, "resume_last", False):
        return True
    if getattr(args, "prompt_words", None):
        return True
    if not sys.stdin.isatty():
        return True
    return False


def _eprint_factory_chat(quiet: bool):
    if quiet:
        return lambda _msg: None
    def _eprint(msg: str) -> None:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    return _eprint


def _chat_error(
    *,
    json_out: bool,
    eprint,
    code: str,
    message: str,
    retryable: bool = False,
    **fields,
) -> int:
    if json_out:
        return emit_error(code, message, retryable=retryable, **fields)
    eprint(message)
    return 1


async def _read_existing_task(
    client: TruffleClient,
    stream: Any,
    state: TaskState,
    *,
    timeout: float | None,
    stop_on_pending: bool,
) -> bool:
    async def consume() -> None:
        async for update in stream:
            _print_update(update, state, quiet=True)
            if (stop_on_pending and state.pending_node_id is not None) or state.run_state:
                break

    try:
        if timeout is not None:
            await asyncio.wait_for(consume(), timeout=max(0.1, timeout))
        else:
            await consume()
        return False
    except asyncio.TimeoutError:
        if state.task_id:
            try:
                await client.interrupt_task(state.task_id)
            except Exception:
                pass
        return True


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
    return "\n\n".join(p for p in parts if p)


def _resolve_app_refs(refs: list[str], apps_list: list[dict]) -> tuple[list[dict], list[str]]:
    """Resolve --app values (name, slug, or uuid) to app dicts.

    Returns (matched, unmatched). Match order: exact uuid → exact name (case-insensitive)
    → slug (lowercased name with spaces→hyphens) → substring on name.
    """
    matched: list[dict] = []
    unmatched: list[str] = []
    for ref in refs:
        ref_s = ref.strip()
        if not ref_s:
            continue
        ref_l = ref_s.lower()
        hit: dict | None = None
        for a in apps_list:
            if a.get("uuid") == ref_s:
                hit = a
                break
        if hit is None:
            for a in apps_list:
                if a.get("name", "").lower() == ref_l:
                    hit = a
                    break
        if hit is None:
            for a in apps_list:
                slug = a.get("name", "").lower().replace(" ", "-")
                if slug == ref_l:
                    hit = a
                    break
        if hit is None:
            for a in apps_list:
                if ref_l in a.get("name", "").lower():
                    hit = a
                    break
        if hit is not None:
            matched.append(hit)
        else:
            unmatched.append(ref_s)
    return matched, unmatched


async def _run_oneshot_chat(args, storage: StorageService) -> int:
    quiet = bool(getattr(args, "quiet", False))
    eprint = _eprint_factory_chat(quiet)
    json_out = bool(getattr(args, "json", False))
    timeout = getattr(args, "timeout", None)

    device, ip = await _resolve_connected_device(storage, quiet=json_out)
    if not device or not ip:
        return _chat_error(
            json_out=json_out,
            eprint=eprint,
            code="device_unreachable",
            message="The connected Truffle device could not be resolved",
            retryable=True,
            next_action="Run truffile scan --json, then reconnect if needed",
        )

    token = storage.get_token(device)
    if not token:
        return _chat_error(
            json_out=json_out,
            eprint=eprint,
            code="missing_token",
            message=f"No saved session token for {device}",
            device=device,
            next_action=f"Run truffile connect {device} --user-id <user-id> --json",
        )

    client = TruffleClient(f"{ip}:80", token=token, app_id=storage.app_id_for_device(device))
    try:
        try:
            await client.connect()
            await client.check_auth()
        except Exception as exc:
            return _chat_error(
                json_out=json_out,
                eprint=eprint,
                code="connection_failed",
                message=f"Could not connect to {device}: {exc}",
                retryable=True,
                device=device,
            )

        # --list-apps short circuit
        if getattr(args, "list_apps", False):
            try:
                apps_list = await _get_apps_list(client)
            except Exception as exc:
                return _chat_error(
                    json_out=json_out,
                    eprint=eprint,
                    code="list_apps_failed",
                    message=f"Failed to list apps: {exc}",
                    retryable=True,
                    device=device,
                )
            if json_out:
                emit_json(ok_payload(device=device, apps=apps_list))
            else:
                for a in apps_list:
                    slug = a.get("name", "").lower().replace(" ", "-")
                    print(f"{slug}\t{a.get('name', '')}\t{a.get('uuid', '')}")
            return 0

        # --list-tasks short circuit
        if getattr(args, "list_tasks", None) is not None:
            n = int(getattr(args, "list_tasks", 15) or 15)
            try:
                tasks = await client.get_task_infos(max_before=n)
            except Exception as exc:
                return _chat_error(
                    json_out=json_out,
                    eprint=eprint,
                    code="list_tasks_failed",
                    message=f"Failed to list tasks: {exc}",
                    retryable=True,
                    device=device,
                )
            if json_out:
                emit_json(ok_payload(device=device, tasks=tasks))
            else:
                for t in tasks:
                    tid = t.get("task_id", "")
                    title = t.get("title", "") or "(untitled)"
                    updated = (t.get("updated") or "")[:16]
                    print(f"{tid}\t{updated}\t{title}")
            return 0

        # apps to attach
        attach_uuids: list[str] = []
        attach_names: list[str] = []
        app_refs = getattr(args, "app", None) or []
        if app_refs:
            try:
                apps_list = await _get_apps_list(client)
            except Exception as exc:
                return _chat_error(
                    json_out=json_out,
                    eprint=eprint,
                    code="list_apps_failed",
                    message=f"Failed to list apps: {exc}",
                    retryable=True,
                    device=device,
                )
            matched, unmatched = _resolve_app_refs(app_refs, apps_list)
            if unmatched:
                return _chat_error(
                    json_out=json_out,
                    eprint=eprint,
                    code="app_not_found",
                    message=f"Unknown app(s): {', '.join(unmatched)}",
                    apps=unmatched,
                )
            attach_uuids = [a["uuid"] for a in matched]
            attach_names = [a.get("name", "") for a in matched]
            for name in attach_names:
                eprint(f"{CHECK} attached: {name}")

        # resolve target task: --task-id, --resume-last, or new
        target_task_id: str | None = getattr(args, "task_id", None)
        if not target_task_id and getattr(args, "resume_last", False):
            try:
                tasks = await client.get_task_infos(max_before=1)
            except Exception as exc:
                return _chat_error(
                    json_out=json_out,
                    eprint=eprint,
                    code="list_tasks_failed",
                    message=f"Failed to fetch tasks: {exc}",
                    retryable=True,
                    device=device,
                )
            if not tasks:
                return _chat_error(
                    json_out=json_out,
                    eprint=eprint,
                    code="task_not_found",
                    message="No previous tasks to resume",
                )
            target_task_id = tasks[0].get("task_id")
            eprint(f"resuming task {target_task_id}")

        # read prompt (may be empty if user is just resuming to peek)
        try:
            prompt_text = _read_chat_prompt(args)
        except FileNotFoundError as exc:
            return _chat_error(
                json_out=json_out,
                eprint=eprint,
                code="file_not_found",
                message=str(exc),
            )

        state = TaskState()

        if target_task_id and not prompt_text:
            # resume + dump current state, no new message
            state.task_id = target_task_id
            stream = client.open_existing_task_stream(target_task_id)
            try:
                timed_out = await _read_existing_task(
                    client,
                    stream,
                    state,
                    timeout=timeout,
                    stop_on_pending=False,
                )
            except Exception as exc:
                return _chat_error(
                    json_out=json_out,
                    eprint=eprint,
                    code="task_read_failed",
                    message=f"Failed to read task {target_task_id}: {exc}",
                    retryable=True,
                    task_id=target_task_id,
                )
            if timed_out:
                return _chat_error(
                    json_out=json_out,
                    eprint=eprint,
                    code="timeout",
                    message=f"Timed out waiting for task {target_task_id}",
                    retryable=True,
                    task_id=target_task_id,
                )
        elif target_task_id and prompt_text:
            # resume + send follow-up
            state.task_id = target_task_id
            stream = client.open_existing_task_stream(target_task_id)
            try:
                timed_out = await _read_existing_task(
                    client,
                    stream,
                    state,
                    timeout=timeout,
                    stop_on_pending=True,
                )
            except Exception as exc:
                return _chat_error(
                    json_out=json_out,
                    eprint=eprint,
                    code="task_read_failed",
                    message=f"Failed to read task {target_task_id}: {exc}",
                    retryable=True,
                    task_id=target_task_id,
                )
            if timed_out:
                return _chat_error(
                    json_out=json_out,
                    eprint=eprint,
                    code="timeout",
                    message=f"Timed out waiting for task {target_task_id}",
                    retryable=True,
                    task_id=target_task_id,
                )
            if attach_uuids:
                try:
                    await client.set_task_apps(target_task_id, attach_uuids)
                except Exception as exc:
                    return _chat_error(
                        json_out=json_out,
                        eprint=eprint,
                        code="app_attach_failed",
                        message=f"Failed to attach apps: {exc}",
                        task_id=target_task_id,
                    )
            if state.pending_node_id is not None:
                await client.respond_to_task(target_task_id, state.pending_node_id, prompt_text)
                state.pending_node_id = None
                state.pending_source_node_id = None
                if stream is not None:
                    timed_out = await _stream_task(
                        client,
                        stream,
                        state,
                        quiet=True,
                        timeout=timeout,
                    )
            else:
                # task is idle — open a fresh stream with the new prompt
                new_stream = client.open_task_stream(prompt_text, app_uuids=attach_uuids or None)
                state = TaskState()
                timed_out = await _stream_task(
                    client,
                    new_stream,
                    state,
                    quiet=True,
                    timeout=timeout,
                )
        else:
            # new task
            if not prompt_text:
                return _chat_error(
                    json_out=json_out,
                    eprint=eprint,
                    code="input_required",
                    message="No prompt provided (positional, --prompt-file, --stdin, --task-id, or --resume-last required)",
                )
            stream = client.open_task_stream(prompt_text, app_uuids=attach_uuids or None)
            timed_out = await _stream_task(
                client,
                stream,
                state,
                quiet=True,
                timeout=timeout,
            )

        if timed_out:
            return _chat_error(
                json_out=json_out,
                eprint=eprint,
                code="timeout",
                message="Timed out waiting for the task to settle",
                retryable=True,
                task_id=state.task_id or None,
            )
        if state.error_message:
            return _chat_error(
                json_out=json_out,
                eprint=eprint,
                code="task_failed",
                message=state.error_message,
                task_id=state.task_id or None,
            )

        # build final response from accumulated state
        streamed_text = "".join(_streaming_text).strip()
        final_text = streamed_text or state.result_text or ""
        max_output_bytes = max(1, int(getattr(args, "max_output_bytes", 65536) or 65536))
        bounded_text, truncated, original_bytes = truncate_text(final_text, max_output_bytes)

        if json_out:
            payload = ok_payload(
                task_id=state.task_id,
                title=state.title,
                device=device,
                content=bounded_text,
                content_bytes=original_bytes,
                returned_bytes=len(bounded_text.encode("utf-8")),
                truncated=truncated,
                run_state=state.run_state or None,
                task_status=(
                    state.run_state.removeprefix("TASK_RUN_STATE_").lower()
                    if state.run_state
                    else None
                ),
                pending_user_response=state.pending_node_id is not None,
                attached_apps=attach_names or None,
            )
            if bool(getattr(args, "full", False)) or bool(getattr(args, "include_thinking", False)):
                payload["thinking"] = state.thinking_summaries or None
            if bool(getattr(args, "full", False)) or bool(getattr(args, "include_tools", False)):
                payload["tool_calls"] = state.tool_calls or None
            emit_json(payload)
        else:
            if getattr(args, "show_thinking", False) and state.thinking_summaries:
                sys.stderr.write("--- thinking ---\n")
                sys.stderr.write(" ".join(state.thinking_summaries) + "\n")
                sys.stderr.write("--- end thinking ---\n")
            if bounded_text:
                print(bounded_text)
            if truncated:
                eprint(f"response truncated at {max_output_bytes} bytes (original {original_bytes} bytes)")
        return 0
    finally:
        try:
            await client.close()
        except Exception:
            pass


async def cmd_chat(args, storage: StorageService) -> int:
    if _is_oneshot_chat(args):
        return await _run_oneshot_chat(args, storage)

    result = await _resolve_connected_device(storage)
    device, ip = result
    if not device or not ip:
        return 1

    token = storage.get_token(device)
    if not token:
        error(f"no token for {device}")
        return 1

    address = f"{ip}:80"
    client = TruffleClient(address, token=token, app_id=storage.app_id_for_device(device))

    spinner = Spinner(f"Connecting to {device}")
    spinner.start()
    try:
        await client.connect()
        await client.check_auth()
        spinner.stop(success=True)
    except Exception as e:
        spinner.fail(f"Could not connect to {device}")
        error(str(e))
        return 1

    resume = getattr(args, "resume", False)
    state = TaskState()
    stream = None

    # create prompt first so the refresh helper can populate its completer
    prompt = TrufflePrompt("you> ", CHAT_COMMANDS)
    prompt.task_name = state.title

    # fetch installed apps and register as /<appname> slash commands
    app_commands: dict[str, dict] = {}
    app_slugs = await _refresh_app_commands(client, app_commands, prompt)

    # welcome panel
    show_chat_welcome(device=device, apps=app_slugs or None)

    if resume:
        task_id = await _pick_task(client)
        if task_id:
            state.task_id = task_id
            stream = client.open_existing_task_stream(task_id)
            try:
                async for update in stream:
                    _print_update(update, state)
                    if state.run_state:
                        break
            except Exception:
                pass
            info(f"resumed \"{state.title or 'task'}\"")
            prompt.task_name = state.title

    try:
        while True:
            user_input = await prompt.get_input()
            if user_input is None:
                print()
                break
            if not user_input.strip():
                continue

            stripped = user_input.strip()
            attach_app: dict | None = None  # set when user typed /<appname> <prompt>

            if stripped.startswith("/"):
                parts = stripped.split(maxsplit=1)
                cmd_name = parts[0].lower()
                arg = parts[1].strip() if len(parts) > 1 else ""

                # /<appname> <prompt> shortcut: attach the app and use <prompt>
                # as the user message in the same turn.
                if arg and app_commands and cmd_name in app_commands:
                    attach_app = app_commands[cmd_name]
                    stripped = arg
                else:
                    action = await _handle_slash(stripped, client, state, storage, app_commands=app_commands)
                    if action == "exit":
                        break
                    if action == "new":
                        state = TaskState()
                        stream = None
                        prompt.task_name = ""
                        info("starting new conversation")
                        continue
                    if action == "refresh_apps":
                        await _refresh_app_commands(client, app_commands, prompt)
                        continue
                    if action and action.startswith("switch:"):
                        new_task_id = action.split(":", 1)[1]
                        state = TaskState()
                        state.task_id = new_task_id
                        stream = client.open_existing_task_stream(new_task_id)
                        try:
                            async for update in stream:
                                _print_update(update, state)
                                if state.run_state:
                                    break
                        except Exception:
                            pass
                        prompt.task_name = state.title
                        info(f"switched to \"{state.title or 'task'}\"")
                        print()
                    continue

            print()

            orb = create_thinking_orb()
            attach_uuids = [attach_app["uuid"]] if attach_app else None

            if state.pending_node_id is not None:
                if attach_app:
                    try:
                        await client.set_task_apps(state.task_id, [attach_app["uuid"]])
                        success(f"added {attach_app['name']} to task")
                    except Exception as e:
                        error(f"failed to add {attach_app['name']}: {e}")
                await client.respond_to_task(state.task_id, state.pending_node_id, stripped)
                state.pending_node_id = None
                state.pending_source_node_id = None
                if stream:
                    await _stream_task(client, stream, state, orb=orb)
            elif not state.task_id:
                if attach_app:
                    success(f"added {attach_app['name']} to task")
                stream = client.open_task_stream(stripped, app_uuids=attach_uuids)
                await _stream_task(client, stream, state, orb=orb)
            else:
                state = TaskState()
                if attach_app:
                    success(f"added {attach_app['name']} to task")
                stream = client.open_task_stream(stripped, app_uuids=attach_uuids)
                await _stream_task(client, stream, state, orb=orb)

            # update task name for prompt border
            prompt.task_name = state.title

            streamed = "".join(_streaming_text)

            if streamed and state.thinking_summaries:
                # clear raw streamed text, reprint with thinking above
                try:
                    width = shutil.get_terminal_size().columns
                except Exception:
                    width = 80
                from .markdown import count_terminal_lines
                nlines = count_terminal_lines(streamed, width)
                sys.stdout.write(f"\r\033[{nlines}A")
                for _ in range(nlines + 1):
                    sys.stdout.write("\033[K\n")
                sys.stdout.write(f"\033[{nlines + 1}A")
                sys.stdout.flush()
                # thinking header
                combined = " ".join(state.thinking_summaries)
                print(f"{C.GRAY}thinking: {combined}{C.RESET}")
                # reprint response (was cleared above)
                print(streamed)
                _maybe_render_markdown(streamed)
            elif streamed:
                # content already printed during streaming, just finish the line
                print()
                _maybe_render_markdown(streamed)
            elif state.thinking_summaries:
                # thinking but no streamed content
                combined = " ".join(state.thinking_summaries)
                print(f"{C.GRAY}thinking: {combined}{C.RESET}")
                if state.result_text:
                    print(state.result_text)
            elif state.result_text:
                # non-streaming result
                print(state.result_text)
            print()

    except KeyboardInterrupt:
        if state.task_id:
            try:
                await client.interrupt_task(state.task_id)
            except Exception:
                pass
    finally:
        await client.close()
        print(f"\n{MUSHROOM} goodbye!")

    return 0
