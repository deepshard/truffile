from __future__ import annotations

from pathlib import Path
from typing import Any


def _normalize_cmd(cmd_list: list[str]) -> tuple[str, list[str]]:
    if not cmd_list:
        return ("", [])
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
        raise RuntimeError("app must define foreground and/or background process config")

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

    ordered_steps = []
    for step in config.get("steps", []):
        if isinstance(step, dict):
            ordered_steps.append(step)

    if config.get("files"):
        ordered_steps.append({"type": "files", "name": "Copy files", "files": config["files"]})
    if config.get("run"):
        ordered_steps.append({"type": "bash", "name": "Install dependencies", "run": config["run"]})

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
        "ordered_steps": ordered_steps,
        "files_to_upload": [f for s in ordered_steps if s.get("type") == "files" for f in s.get("files", [])],
        "bash_commands": [(s.get("name", "bash"), s["run"]) for s in ordered_steps if s.get("type") == "bash"],
    }
