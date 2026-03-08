from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from truffile.transport.client import TruffleClient


def _normalize_cmd(cmd_list: list[str]) -> tuple[str, list[str]]:
    cmd = cmd_list[0] if cmd_list[0].startswith("/") else f"/usr/bin/{cmd_list[0]}"
    return cmd, cmd_list[1:]


def _env_map_to_list(env_dict: dict[str, str] | None) -> list[str]:
    if not env_dict:
        return []
    return [f"{k}={v}" for k, v in env_dict.items()]


def _bundle_id_from_name(name: str) -> str:
    raw = "".join(ch.lower() if ch.isalnum() else "." for ch in name).strip(".")
    normalized = ".".join([part for part in raw.split(".") if part])
    return normalized or "truffle.app"


def _extract_process(process_cfg: dict[str, Any] | None) -> tuple[str, list[str], str, list[str]]:
    proc = process_cfg or {}
    cmd_list = list(proc.get("cmd", ["python", "app.py"]))
    cmd, args = _normalize_cmd(cmd_list)
    cwd = proc.get("working_directory", proc.get("cwd", "/"))
    env = _env_map_to_list(proc.get("environment", proc.get("env")))
    return cmd, args, cwd, env


def build_deploy_plan(
    *,
    config: dict[str, Any],
    app_dir: Path,
    app_type: str,
) -> dict[str, Any]:
    meta = config["metadata"]
    name = meta["name"]
    description = meta.get("description", "")
    bundle_id = meta.get("bundle_id") or _bundle_id_from_name(name)
    icon_file = meta.get("icon_file")
    icon_path = (app_dir / icon_file) if icon_file and (app_dir / icon_file).exists() else None

    fg_cfg = meta.get("foreground")
    bg_cfg = meta.get("background")
    new_style = isinstance(fg_cfg, dict) or isinstance(bg_cfg, dict)

    if new_style:
        has_fg = isinstance(fg_cfg, dict)
        has_bg = isinstance(bg_cfg, dict)
    else:
        has_fg = app_type == "focus"
        has_bg = app_type == "ambient"

    if not has_fg and not has_bg:
        raise RuntimeError("App must define foreground and/or background process config")

    fg_payload = None
    bg_payload = None
    exec_cwd = "/"
    if has_fg:
        fg_process = fg_cfg.get("process") if isinstance(fg_cfg, dict) else meta.get("process")
        fg_cmd, fg_args, fg_cwd, fg_env = _extract_process(fg_process)
        fg_payload = {"cmd": fg_cmd, "args": fg_args, "cwd": fg_cwd, "env": fg_env}
        exec_cwd = fg_cwd
    if has_bg:
        bg_process = bg_cfg.get("process") if isinstance(bg_cfg, dict) else meta.get("process")
        bg_cmd, bg_args, bg_cwd, bg_env = _extract_process(bg_process)
        bg_payload = {"cmd": bg_cmd, "args": bg_args, "cwd": bg_cwd, "env": bg_env}
        if exec_cwd == "/" and bg_cwd:
            exec_cwd = bg_cwd

    if has_fg and has_bg:
        finish_label = "foreground+background"
    elif has_fg:
        finish_label = "foreground"
    else:
        finish_label = "background"

    default_schedule = None
    if isinstance(bg_cfg, dict):
        default_schedule = bg_cfg.get("default_schedule")
    elif has_bg:
        default_schedule = meta.get("default_schedule")

    files_to_upload = []
    for step in config.get("steps", []):
        if isinstance(step, dict) and step.get("type") == "files":
            files_to_upload.extend(step.get("files", []))
    files_to_upload.extend(config.get("files", []))

    bash_commands = []
    for step in config.get("steps", []):
        if isinstance(step, dict) and step.get("type") == "bash":
            bash_commands.append((step.get("name", "bash"), step["run"]))
    if config.get("run"):
        bash_commands.append(("Install dependencies", config["run"]))

    return {
        "name": name,
        "description": description,
        "bundle_id": bundle_id,
        "icon_path": icon_path,
        "fg_payload": fg_payload,
        "bg_payload": bg_payload,
        "exec_cwd": exec_cwd,
        "finish_label": finish_label,
        "default_schedule": default_schedule,
        "files_to_upload": files_to_upload,
        "bash_commands": bash_commands,
    }


async def _wait_for_build_session_ready(client: TruffleClient, timeout_sec: float = 45.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last_error: Exception | None = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            result = await client.exec("echo ready", cwd="/")
            if result.exit_code == 0:
                return
        except Exception as e:
            last_error = e
        await asyncio.sleep(1.0)
    if last_error is not None:
        raise RuntimeError(f"build session endpoint did not become ready in time: {last_error}")
    raise RuntimeError("build session endpoint did not become ready in time")


async def deploy_with_builder(
    *,
    client: TruffleClient,
    config: dict[str, Any],
    app_dir: Path,
    app_type: str,
    device: str,
    interactive: bool,
    spinner_cls: Any,
    scrolling_log_cls: Any,
    info: Callable[[str], None],
    success: Callable[[str], None],
    error: Callable[[str], None],
    color_dim: str,
    color_reset: str,
    color_bold: str,
    arrow: str,
    interactive_shell: Callable[[str], Any],
) -> int:
    plan = build_deploy_plan(config=config, app_dir=app_dir, app_type=app_type)
    name = plan["name"]
    description = plan["description"]
    bundle_id = plan["bundle_id"]
    icon_path = plan["icon_path"]
    fg_payload = plan["fg_payload"]
    bg_payload = plan["bg_payload"]
    exec_cwd = plan["exec_cwd"]
    finish_label = plan["finish_label"]
    default_schedule = plan["default_schedule"]
    files_to_upload = plan["files_to_upload"]
    bash_commands = plan["bash_commands"]

    spinner = spinner_cls(f"Connecting to {device}")
    spinner.start()
    await client.connect()
    spinner.stop(success=True)

    spinner = spinner_cls("Starting build session")
    spinner.start()
    await client.start_build()
    await _wait_for_build_session_ready(client)
    spinner.stop(success=True)
    print(f"  {color_dim}Session: {client.app_uuid}{color_reset}")

    for f in files_to_upload:
        src = app_dir / f["source"]
        dest = f["destination"]
        spinner = spinner_cls(f"Uploading {src.name} {arrow} {dest}")
        spinner.start()
        result = await client.upload(src, dest)
        spinner.stop(success=True)
        print(f"  {color_dim}{result.bytes} bytes, sha256={result.sha256[:12]}...{color_reset}")

    for step_name, run_cmd in bash_commands:
        info(f"Running: {step_name}")
        log = scrolling_log_cls(height=6, prefix="  ")
        exit_code = 0
        async for ev, data in client.exec_stream(run_cmd, cwd=exec_cwd):
            if ev == "log":
                try:
                    import json
                    obj = json.loads(data)
                    line = obj.get("line", "")
                except Exception:
                    line = data
                log.add(line)
            elif ev == "exit":
                try:
                    import json
                    exit_code = int(json.loads(data).get("code", 0))
                except (ValueError, KeyError):
                    pass
        log.finish()
        if exit_code != 0:
            error(f"Step '{step_name}' failed with exit code {exit_code}")
            raise RuntimeError(f"Step '{step_name}' failed with exit code {exit_code}")

    if interactive:
        print()
        info("Opening interactive shell (exit with Ctrl+D or 'exit' to finish deploy)")
        ws_url = str(client.http_base or "").replace("http://", "ws://").replace("https://", "wss://") + "/term"
        await interactive_shell(ws_url)
        print()

    spinner = spinner_cls(f"Finishing as {finish_label} app")
    spinner.start()

    await client.finish_app(
        name=name,
        bundle_id=bundle_id,
        description=description,
        icon=icon_path,
        foreground=fg_payload,
        background=bg_payload,
        default_schedule=default_schedule,
    )

    spinner.stop(success=True)
    print()
    success(f"Deployed: {color_bold}{name}{color_reset} ({finish_label})")
    return 0
