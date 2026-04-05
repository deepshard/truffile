from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from truffile.storage import StorageService
from truffile.client import TruffleClient, resolve_mdns
from .ui import C, MUSHROOM, DOT, CHECK, CROSS, Spinner, ScrollingLog, error, success, info, warn
from .connect import _resolve_connected_device
from .picker import pick_from_list


@dataclass
class TaskState:
    task_id: str = ""
    title: str = ""
    run_state: str = ""
    pending_node_id: int | None = None
    result_text: str = ""
    tool_calls: list[str] = field(default_factory=list)


CHAT_COMMANDS = {
    "/help": "show available commands",
    "/tasks": "list recent tasks",
    "/rename <name>": "rename current task",
    "/title": "show current task title",
    "/resume": "switch to a previous task",
    "/new": "start a new task",
    "/apps": "list installed apps",
    "/app <name>": "add an app to current task",
    "/deploy <path>": "deploy an app to device",
    "/delete app <name>": "delete an installed app",
    "/delete task": "delete current task",
    "/devices": "list connected devices",
    "/exit": "exit chat",
}


def _print_update(update: Any, state: TaskState) -> None:
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
        print(f"\n{C.RED}error: {msg}{C.RESET}")

    if update.HasField("streaming_step_result"):
        chunk = update.streaming_step_result.partial_content
        if chunk:
            sys.stdout.write(chunk)
            sys.stdout.flush()

    for node in update.nodes:
        if not node.HasField("step"):
            continue

        step = node.step

        if step.HasField("thinking"):
            for s in step.thinking.cot_summaries:
                print(f"{C.DIM}thinking: {s}{C.RESET}")

        for tc in step.tool_calls:
            name = tc.tool_name if hasattr(tc, "tool_name") else ""
            tc_summary = tc.summary if hasattr(tc, "summary") else ""
            if name:
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

        if step.HasField("user_response"):
            node_id = step.user_response.node_id if hasattr(step.user_response, "node_id") else 0
            if node_id:
                state.pending_node_id = node_id


async def _stream_task(client: TruffleClient, stream: Any, state: TaskState) -> None:
    interrupted = False
    try:
        async for update in stream:
            _print_update(update, state)
            if state.pending_node_id is not None:
                break
    except (asyncio.CancelledError, KeyboardInterrupt):
        interrupted = True
    except Exception:
        interrupted = True

    if interrupted and state.task_id:
        print(f"\n{C.DIM}interrupting...{C.RESET}")
        try:
            await client.interrupt_task(state.task_id)
        except Exception:
            pass


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
    picked = pick_from_list(
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


async def _handle_slash(
    cmd: str,
    client: TruffleClient,
    state: TaskState,
    storage: StorageService,
) -> str | None:
    """returns action string or None. 'exit' to quit, 'new' for fresh task, 'switch:<id>' to resume."""

    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command == "/help":
        print(f"\n{C.BOLD}commands:{C.RESET}")
        for name, desc in CHAT_COMMANDS.items():
            print(f"  {C.CYAN}{name}{C.RESET} — {desc}")
        print()
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

    if command == "/tasks":
        tasks = await client.get_task_infos(max_before=10)
        if not tasks:
            info("no tasks found")
            return None
        print()
        for i, t in enumerate(tasks, 1):
            marker = f" {C.GREEN}(current){C.RESET}" if t["task_id"] == state.task_id else ""
            updated = t["updated"][:16] if t["updated"] else ""
            print(f"  {C.CYAN}{i}.{C.RESET} {t['title']}{marker} {C.DIM}{updated}{C.RESET}")
        print()
        return None

    if command in ("/resume", "/switch"):
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
            print(f"\n{C.BOLD}Installed apps:{C.RESET}")
            for a in apps_list:
                print(f"  {C.CYAN}{DOT}{C.RESET} {a['name']} {C.DIM}({a['bundle_id']}){C.RESET}")
            print()
        except Exception as e:
            error(f"failed to list apps: {e}")
        return None

    if command == "/app":
        if not arg:
            error("usage: /app <name>")
            return None
        if not state.task_id:
            error("no active task — send a message first")
            return None
        try:
            apps_list = await _get_apps_list(client)
            match = _find_app_by_name(apps_list, arg)
            if not match:
                error(f"app \"{arg}\" not found. use /apps to see installed apps.")
                return None
            await client.set_task_apps(state.task_id, [match["uuid"]])
            success(f"added {match['name']} to task")
        except Exception as e:
            error(f"failed: {e}")
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
                    picked = pick_from_list(items, label_key="label", detail_key="detail", prompt="pick app to delete")
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

    error(f"unknown command: {command}. type /help")
    return None


async def cmd_chat(args, storage: StorageService) -> int:
    result = await _resolve_connected_device(storage)
    device, ip = result
    if not device or not ip:
        return 1

    token = storage.get_token(device)
    if not token:
        error(f"no token for {device}")
        return 1

    address = f"{ip}:80"
    client = TruffleClient(address, token=token)

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
            print(f"\n{C.BOLD}{MUSHROOM} truffile chat{C.RESET} — resumed \"{state.title or 'task'}\"")
        else:
            print(f"\n{C.BOLD}{MUSHROOM} truffile chat{C.RESET} — connected to {device}")
    else:
        print(f"\n{C.BOLD}{MUSHROOM} truffile chat{C.RESET} — connected to {device}")

    print(f"{C.DIM}type a message or /help for commands. ctrl+c to interrupt. ctrl+d to exit.{C.RESET}\n")

    try:
        while True:
            try:
                user_input = input(f"{C.BOLD}you>{C.RESET} ")
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_input.strip():
                continue

            if user_input.strip().startswith("/"):
                action = await _handle_slash(user_input.strip(), client, state, storage)
                if action == "exit":
                    break
                if action == "new":
                    state = TaskState()
                    stream = None
                    info("starting new conversation")
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
                    info(f"switched to \"{state.title or 'task'}\"")
                    print()
                continue

            print()

            if state.pending_node_id is not None:
                await client.respond_to_task(state.task_id, state.pending_node_id, user_input.strip())
                state.pending_node_id = None
                if stream:
                    await _stream_task(client, stream, state)
            elif not state.task_id:
                stream = client.open_task_stream(user_input.strip())
                await _stream_task(client, stream, state)
            else:
                state = TaskState()
                stream = client.open_task_stream(user_input.strip())
                await _stream_task(client, stream, state)

            if state.result_text:
                print(f"\n{state.result_text}")
            print()

    except KeyboardInterrupt:
        print()
        if state.task_id:
            try:
                await client.interrupt_task(state.task_id)
            except Exception:
                pass
    finally:
        await client.close()

    return 0
