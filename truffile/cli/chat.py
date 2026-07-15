from __future__ import annotations

import asyncio
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import grpc

from truffile.storage import StorageService
from truffile.client import TruffleClient
from .ui import C, MUSHROOM, DOT, CHECK, Spinner, ScrollingLog, StreamAbortWatcher, error, success, info, create_thinking_orb
from .connect import _grpc_address, _resolve_connected_device
from .picker import pick_from_list
from .commands import CHAT_COMMANDS, SlashCommand
from .prompt import TrufflePrompt
from .markdown import has_markdown, render_markdown, count_terminal_lines
from .art import ParticleOrb
from .exit_codes import CONNECTION, CONFLICT, ERROR, NOT_FOUND, SUCCESS, TIMEOUT, USAGE
from .welcome import show_chat_welcome


@dataclass
class TaskState:
    task_id: str = ""
    title: str = ""
    run_state: str = ""
    created: str = ""
    updated: str = ""
    pending_node_id: int | None = None
    result_text: str = ""
    tool_calls: list[str] = field(default_factory=list)
    thinking_summaries: list[str] = field(default_factory=list)


# accumulated streaming text for markdown re-render
_streaming_text: list[str] = []


def _apply_task_info(info: Any, state: TaskState) -> None:
    run_state = info.TaskRunState.Name(info.run_state) if info.run_state else ""
    if run_state:
        state.run_state = run_state
    if info.task_title:
        state.title = info.task_title
    if info.HasField("created"):
        state.created = info.created.ToDatetime().isoformat()
    if info.HasField("last_updated"):
        state.updated = info.last_updated.ToDatetime().isoformat()


def _apply_task_nodes(
    nodes: Any,
    state: TaskState,
    *,
    quiet: bool = False,
    emit_tools: bool = True,
    interrupt_on_cancel: bool = True,
) -> None:
    for node in nodes:
        if not node.HasField("step"):
            continue

        step = node.step

        if step.HasField("thinking"):
            for summary in step.thinking.cot_summaries:
                if summary not in state.thinking_summaries:
                    state.thinking_summaries.append(summary)

        for tool_call in step.tool_calls:
            name = tool_call.tool_name if hasattr(tool_call, "tool_name") else ""
            summary = tool_call.summary if hasattr(tool_call, "summary") else ""
            if name and emit_tools:
                if quiet:
                    if summary:
                        sys.stderr.write(f"{DOT} tool: {name} — {summary}\n")
                    else:
                        sys.stderr.write(f"{DOT} tool: {name}\n")
                else:
                    print(f"{C.CYAN}{DOT} tool: {name}{C.RESET}", end="")
                    if summary:
                        print(f" {C.DIM}— {summary}{C.RESET}")
                    else:
                        print()
            if name:
                state.tool_calls.append(name)

        if step.HasField("results"):
            content = step.results.content if hasattr(step.results, "content") else ""
            summary = step.results.summary if hasattr(step.results, "summary") else ""
            text = content or summary
            if text:
                state.result_text = text

        if step.HasField("user_response"):
            node_id = step.user_response.node_id if hasattr(step.user_response, "node_id") else 0
            if node_id:
                state.pending_node_id = node_id


def _apply_task_snapshot(
    task: Any,
    state: TaskState,
    *,
    quiet: bool = False,
    emit_tools: bool = False,
) -> None:
    if task.task_id:
        state.task_id = task.task_id
    if task.HasField("info"):
        _apply_task_info(task.info, state)
    _apply_task_nodes(task.nodes, state, quiet=quiet, emit_tools=emit_tools)


def _task_status(state: TaskState) -> str:
    if state.pending_node_id is not None:
        return "waiting_for_user"
    prefix = "TASK_RUN_STATE_"
    if state.run_state:
        return state.run_state.removeprefix(prefix).lower()
    return "unknown"


def _state_payload(
    state: TaskState,
    *,
    device: str,
    content: str,
    operation: str,
    attached_apps: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "task_id": state.task_id,
        "title": state.title,
        "device": device,
        "operation": operation,
        "status": _task_status(state),
        "run_state": state.run_state or None,
        "created": state.created or None,
        "updated": state.updated or None,
        "content": content.strip(),
        "thinking": state.thinking_summaries or None,
        "tool_calls": state.tool_calls or None,
        "pending_user_response": state.pending_node_id is not None,
        "attached_apps": attached_apps or None,
    }


def _emit_oneshot_error(
    message: str,
    *,
    json_out: bool,
    code: str,
    device: str | None = None,
    task_id: str | None = None,
) -> None:
    if json_out:
        print(
            json.dumps(
                {
                    "error": {
                        "code": code,
                        "message": message,
                    },
                    "device": device,
                    "task_id": task_id,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        sys.stderr.write(f"error: {message}\n")
        sys.stderr.flush()


def _print_update(
    update: Any,
    state: TaskState,
    *,
    quiet: bool = False,
    emit_tools: bool = True,
) -> None:
    if update.task_id and not state.task_id:
        state.task_id = update.task_id

    if update.HasField("info"):
        _apply_task_info(update.info, state)

    if update.HasField("error"):
        msg = update.error.message if hasattr(update.error, "message") else str(update.error)
        if quiet:
            sys.stderr.write(f"error: {msg}\n")
        else:
            print(f"\n{C.RED}error: {msg}{C.RESET}")

    # Render thinking/tools before streaming content so they appear above it.
    _apply_task_nodes(update.nodes, state, quiet=quiet, emit_tools=emit_tools)

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
    emit_tools: bool = True,
    interrupt_on_cancel: bool = True,
) -> None:
    global _streaming_text
    _streaming_text = []
    interrupted = False
    cancelled = False
    stream_error: Exception | None = None
    orb_stopped = False

    if orb and not quiet:
        orb.start(ParticleOrb.STATE_ACTIVE)

    abort_cm: Any = StreamAbortWatcher() if not quiet else _NullAbort()
    with abort_cm as abort:
        try:
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
                _print_update(update, state, quiet=quiet, emit_tools=emit_tools)
                if state.pending_node_id is not None:
                    break
        except asyncio.CancelledError:
            interrupted = True
            cancelled = True
        except KeyboardInterrupt:
            interrupted = True
        except Exception as exc:
            interrupted = True
            stream_error = exc

    if orb and not orb_stopped and not quiet:
        orb.stop()

    if interrupted and interrupt_on_cancel and state.task_id:
        if not quiet:
            print(f"\n{C.DIM}interrupting...{C.RESET}")
        try:
            await client.interrupt_task(state.task_id)
        except Exception:
            pass
    if cancelled:
        raise asyncio.CancelledError
    if stream_error is not None:
        raise stream_error


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
            from truffile.deploy import deploy_with_builder
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
    if getattr(args, "force_interactive", False):
        return False
    if getattr(args, "force_oneshot", False):
        return True
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

    Returns (matched, unmatched). Match order: exact uuid → exact name
    (case-insensitive) → slug (lowercased name with spaces→hyphens) → unique
    substring on name. Ambiguous substrings are deliberately rejected.
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
            substring_matches = [
                app for app in apps_list if ref_l in app.get("name", "").lower()
            ]
            if len(substring_matches) == 1:
                hit = substring_matches[0]
        if hit is not None:
            matched.append(hit)
        else:
            unmatched.append(ref_s)
    return matched, unmatched


async def _run_oneshot_chat_impl(args, storage: StorageService) -> int:
    global _streaming_text
    _streaming_text = []
    quiet = bool(getattr(args, "quiet", False))
    eprint = _eprint_factory_chat(quiet)
    json_out = bool(getattr(args, "json", False))

    requested_device = getattr(args, "device", None)
    device, ip = await _resolve_connected_device(
        storage,
        requested_device,
        emit_errors=not json_out,
    )
    if not device or not ip:
        _emit_oneshot_error(
            f"could not resolve connected device{f' {requested_device}' if requested_device else ''}",
            json_out=json_out,
            code="connection_error",
            device=requested_device,
        )
        return CONNECTION

    token = storage.get_token(device)
    if not token:
        _emit_oneshot_error(
            f"no token for {device}",
            json_out=json_out,
            code="connection_error",
            device=device,
        )
        return CONNECTION

    client = TruffleClient(_grpc_address(ip), token=token, app_id=storage.app_id_for_device(device))
    try:
        try:
            await client.connect()
            if not await client.check_auth():
                raise PermissionError("authentication failed")
        except Exception as exc:
            _emit_oneshot_error(
                f"could not connect to {device}: {exc}",
                json_out=json_out,
                code="connection_error",
                device=device,
            )
            return CONNECTION

        # --list-apps short circuit
        if getattr(args, "list_apps", False):
            try:
                apps_list = await _get_apps_list(client)
            except Exception as exc:
                _emit_oneshot_error(
                    f"failed to list apps: {exc}",
                    json_out=json_out,
                    code="execution_error",
                    device=device,
                )
                return ERROR
            if json_out:
                print(json.dumps({"apps": apps_list}, indent=2))
            else:
                for a in apps_list:
                    slug = a.get("name", "").lower().replace(" ", "-")
                    print(f"{slug}\t{a.get('name', '')}\t{a.get('uuid', '')}")
            return 0

        # --list-tasks short circuit
        if getattr(args, "list_tasks", None) is not None:
            n = int(getattr(args, "list_tasks", 15) or 15)
            if n < 1:
                _emit_oneshot_error(
                    "--list-tasks must be at least 1",
                    json_out=json_out,
                    code="usage_error",
                    device=device,
                )
                return USAGE
            try:
                tasks = await client.get_task_infos(max_before=n)
            except Exception as exc:
                _emit_oneshot_error(
                    f"failed to list tasks: {exc}",
                    json_out=json_out,
                    code="execution_error",
                    device=device,
                )
                return ERROR
            if json_out:
                print(json.dumps({"tasks": tasks}, indent=2))
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
                _emit_oneshot_error(
                    f"failed to list apps: {exc}",
                    json_out=json_out,
                    code="execution_error",
                    device=device,
                )
                return ERROR
            matched, unmatched = _resolve_app_refs(app_refs, apps_list)
            if unmatched:
                _emit_oneshot_error(
                    f"unknown or ambiguous app(s): {', '.join(unmatched)}",
                    json_out=json_out,
                    code="not_found",
                    device=device,
                )
                return NOT_FOUND
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
                _emit_oneshot_error(
                    f"failed to fetch tasks: {exc}",
                    json_out=json_out,
                    code="execution_error",
                    device=device,
                )
                return ERROR
            if not tasks:
                _emit_oneshot_error(
                    "no previous tasks to resume",
                    json_out=json_out,
                    code="not_found",
                    device=device,
                )
                return NOT_FOUND
            target_task_id = tasks[0].get("task_id")
            eprint(f"resuming task {target_task_id}")

        # read prompt (may be empty if user is just resuming to peek)
        try:
            prompt_text = _read_chat_prompt(args)
        except FileNotFoundError as exc:
            _emit_oneshot_error(
                str(exc),
                json_out=json_out,
                code="not_found",
                device=device,
                task_id=target_task_id,
            )
            return NOT_FOUND

        state = TaskState()
        # Keep a live reference so the outer timeout/error boundary can report
        # a task ID learned from the stream after this coroutine is cancelled.
        args._active_task_state = state
        operation = "run"

        if target_task_id:
            operation = "resume" if prompt_text else "inspect"
            try:
                task = await client.get_task(target_task_id, with_nodes=True)
            except grpc.aio.AioRpcError as exc:
                details = exc.details() or exc.code().name
                missing = exc.code() == grpc.StatusCode.NOT_FOUND or "not found" in details.lower()
                code = NOT_FOUND if missing else ERROR
                error_code = "not_found" if code == NOT_FOUND else "execution_error"
                _emit_oneshot_error(
                    f"could not load task {target_task_id}: {details}",
                    json_out=json_out,
                    code=error_code,
                    device=device,
                    task_id=target_task_id,
                )
                return code
            except Exception as exc:
                _emit_oneshot_error(
                    f"could not load task {target_task_id}: {exc}",
                    json_out=json_out,
                    code="execution_error",
                    device=device,
                    task_id=target_task_id,
                )
                return ERROR

            if not task.task_id:
                _emit_oneshot_error(
                    f"task not found: {target_task_id}",
                    json_out=json_out,
                    code="not_found",
                    device=device,
                    task_id=target_task_id,
                )
                return NOT_FOUND
            _apply_task_snapshot(task, state, quiet=True)

        if target_task_id and prompt_text:
            if state.pending_node_id is None:
                _emit_oneshot_error(
                    f"task {target_task_id} is not waiting for user input (status: {_task_status(state)})",
                    json_out=json_out,
                    code="conflict",
                    device=device,
                    task_id=target_task_id,
                )
                return CONFLICT

            # Open and prime the stream before responding so subsequent events
            # represent the new turn rather than the existing task snapshot.
            stream = client.open_existing_task_stream(target_task_id)
            try:
                async for update in stream:
                    _print_update(update, state, quiet=True, emit_tools=not quiet)
                    break
            except grpc.aio.AioRpcError as exc:
                _emit_oneshot_error(
                    f"could not resume task {target_task_id}: {exc.details() or exc.code().name}",
                    json_out=json_out,
                    code="execution_error",
                    device=device,
                    task_id=target_task_id,
                )
                return ERROR
            if attach_uuids:
                try:
                    await client.set_task_apps(target_task_id, attach_uuids)
                except Exception as exc:
                    _emit_oneshot_error(
                        f"failed to attach apps: {exc}",
                        json_out=json_out,
                        code="execution_error",
                        device=device,
                        task_id=target_task_id,
                    )
                    return ERROR
            await client.respond_to_task(target_task_id, state.pending_node_id, prompt_text)
            state.pending_node_id = None
            await _stream_task(client, stream, state, quiet=True, emit_tools=not quiet)
        elif not target_task_id:
            # new task
            if not prompt_text:
                _emit_oneshot_error(
                    "no prompt provided (positional, --prompt-file, or --stdin required)",
                    json_out=json_out,
                    code="usage_error",
                    device=device,
                )
                return USAGE
            stream = client.open_task_stream(prompt_text, app_uuids=attach_uuids or None)
            await _stream_task(client, stream, state, quiet=True, emit_tools=not quiet)

        # build final response from accumulated state
        streamed_text = "".join(_streaming_text).strip()
        final_text = streamed_text or state.result_text or ""
        ephemeral = bool(getattr(args, "ephemeral", False))
        if ephemeral and state.task_id:
            try:
                await client.delete_task(state.task_id)
            except Exception as exc:
                _emit_oneshot_error(
                    f"task completed but ephemeral cleanup failed: {exc}",
                    json_out=json_out,
                    code="execution_error",
                    device=device,
                    task_id=state.task_id,
                )
                return ERROR

        if json_out:
            payload = _state_payload(
                state,
                device=device,
                content=final_text,
                operation=operation,
                attached_apps=attach_names,
            )
            payload["ephemeral"] = ephemeral
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            if getattr(args, "show_thinking", False) and state.thinking_summaries:
                sys.stderr.write("--- thinking ---\n")
                sys.stderr.write(" ".join(state.thinking_summaries) + "\n")
                sys.stderr.write("--- end thinking ---\n")
            if final_text:
                print(final_text)
        return SUCCESS
    finally:
        try:
            await client.close()
        except Exception:
            pass


async def _run_oneshot_chat(args, storage: StorageService) -> int:
    timeout = getattr(args, "timeout", None)
    json_out = bool(getattr(args, "json", False))
    requested_device = getattr(args, "device", None)
    target_task_id = getattr(args, "task_id", None)
    args._active_task_state = None

    def active_task_id() -> str | None:
        state = getattr(args, "_active_task_state", None)
        return getattr(state, "task_id", None) or target_task_id

    if timeout is not None and timeout <= 0:
        _emit_oneshot_error(
            "--timeout must be greater than zero",
            json_out=json_out,
            code="usage_error",
            device=requested_device,
            task_id=target_task_id,
        )
        return USAGE
    try:
        if timeout is None:
            return await _run_oneshot_chat_impl(args, storage)
        async with asyncio.timeout(timeout):
            return await _run_oneshot_chat_impl(args, storage)
    except TimeoutError:
        _emit_oneshot_error(
            f"agent operation timed out after {timeout:g} seconds",
            json_out=json_out,
            code="timeout",
            device=requested_device,
            task_id=active_task_id(),
        )
        return TIMEOUT
    except Exception as exc:
        _emit_oneshot_error(
            f"agent operation failed: {exc}",
            json_out=json_out,
            code="execution_error",
            device=requested_device,
            task_id=active_task_id(),
        )
        return ERROR


async def cmd_chat(args, storage: StorageService) -> int:
    if _is_oneshot_chat(args):
        return await _run_oneshot_chat(args, storage)

    result = await _resolve_connected_device(storage, getattr(args, "device", None))
    device, ip = result
    if not device or not ip:
        return 1

    token = storage.get_token(device)
    if not token:
        error(f"no token for {device}")
        return 1

    address = _grpc_address(ip)
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
    resume_last = getattr(args, "resume_last", False)
    explicit_task_id = getattr(args, "task_id", None)
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

    if explicit_task_id or resume or resume_last:
        task_id = explicit_task_id
        if resume_last:
            try:
                tasks = await client.get_task_infos(max_before=1)
            except Exception as exc:
                error(f"could not list tasks: {exc}")
                await client.close()
                return ERROR
            if not tasks:
                error("no tasks available to resume")
                await client.close()
                return NOT_FOUND
            task_id = tasks[0].get("task_id")
        elif not task_id:
            task_id = await _pick_task(client)
            if not task_id:
                await client.close()
                return SUCCESS
        if task_id:
            try:
                task = await client.get_task(task_id, with_nodes=True)
                if not task.task_id:
                    raise LookupError(f"task not found: {task_id}")
                _apply_task_snapshot(task, state, quiet=True, emit_tools=False)
                stream = client.open_existing_task_stream(task_id)
                async for update in stream:
                    _print_update(update, state, quiet=True, emit_tools=False)
                    break
            except Exception as exc:
                error(f"could not resume task {task_id}: {exc}")
                await client.close()
                return NOT_FOUND
            info(f"resumed \"{state.title or 'task'}\"")
            prompt.task_name = state.title

    initial_input = " ".join(getattr(args, "prompt_words", None) or []).strip() or None

    try:
        while True:
            if initial_input is not None:
                user_input = initial_input
                initial_input = None
            else:
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
