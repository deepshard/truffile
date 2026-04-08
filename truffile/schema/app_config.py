from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import yaml


def _check_python_syntax(file_path: Path) -> tuple[bool, str]:
    try:
        source = file_path.read_text(encoding="utf-8")
        ast.parse(source)
        return True, ""
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"


_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_SUPPORTED_STEP_TYPES = {"bash", "files", "text"}
_UNSUPPORTED_STEP_HINTS = {
    "oauth": "OAuth is not supported yet — use a 'text' step with a password field to collect an access token.",
    "vnc": "VNC is not supported yet — use a 'text' step to collect credentials instead.",
}


def _validate_process_cfg(
    process: Any,
    *,
    path: str,
    warnings: list[str],
    errors: list[str],
) -> None:
    if not isinstance(process, dict):
        errors.append(f"{path} must be an object")
        return

    cmd = process.get("cmd")
    if not isinstance(cmd, list) or len(cmd) == 0:
        errors.append(f"{path}.cmd must be a non-empty list")
    elif not all(isinstance(v, str) and v.strip() for v in cmd):
        errors.append(f"{path}.cmd must be list[str] with non-empty values")

    for key in ("working_directory", "cwd"):
        if key in process and not isinstance(process.get(key), str):
            errors.append(f"{path}.{key} must be a string")

    env_obj = process.get("environment", process.get("env"))
    if env_obj is None:
        return
    if not isinstance(env_obj, dict):
        errors.append(f"{path}.environment must be a map")
        return
    for k, v in env_obj.items():
        if not isinstance(k, str):
            errors.append(f"{path}.environment keys must be strings")
            continue
        if not _ENV_KEY_RE.match(k):
            warnings.append(f"{path}.environment key '{k}' is non-standard")
        if not isinstance(v, str):
            errors.append(f"{path}.environment['{k}'] must be a string")


def validate_app_dir(app_dir: Path) -> tuple[bool, dict[str, Any] | None, str | None, list[str], list[str]]:
    """Validate app directory and return (valid, config, app_type, warnings, errors)."""
    warnings: list[str] = []
    errors: list[str] = []

    truffile_path = app_dir / "truffile.yaml"
    if not truffile_path.exists():
        errors.append(f"No truffile.yaml found in {app_dir}")
        return False, None, None, warnings, errors

    try:
        config = yaml.safe_load(truffile_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        errors.append(f"Invalid truffile.yaml: {e}")
        return False, None, None, warnings, errors

    if not isinstance(config, dict):
        errors.append("truffile.yaml root must be a mapping")
        return False, None, None, warnings, errors

    meta = config.get("metadata", {})
    if not isinstance(meta, dict):
        errors.append("metadata must be a mapping")
        return False, None, None, warnings, errors

    if not meta.get("name"):
        errors.append("metadata.name is required in truffile.yaml")
        return False, None, None, warnings, errors

    fg_cfg = meta.get("foreground")
    bg_cfg = meta.get("background")
    has_fg_cfg = isinstance(fg_cfg, dict)
    has_bg_cfg = isinstance(bg_cfg, dict)
    if has_fg_cfg or has_bg_cfg:
        if has_fg_cfg and has_bg_cfg:
            app_type = "hybrid"
        elif has_fg_cfg:
            app_type = "focus"
        else:
            app_type = "ambient"
    else:
        cfg_type = str(meta.get("type", "")).lower().strip()
        if cfg_type in ("background", "ambient"):
            app_type = "ambient"
        elif cfg_type in ("foreground", "focus"):
            app_type = "focus"
        else:
            app_type = "focus"
            warnings.append("No type specified in truffile.yaml, defaulting to focus")

    if "bundle_id" not in meta:
        warnings.append("No metadata.bundle_id specified; using derived default from metadata.name")

    if has_fg_cfg:
        process = fg_cfg.get("process")
        _validate_process_cfg(
            process,
            path="metadata.foreground.process",
            warnings=warnings,
            errors=errors,
        )

    if has_bg_cfg:
        process = bg_cfg.get("process")
        _validate_process_cfg(
            process,
            path="metadata.background.process",
            warnings=warnings,
            errors=errors,
        )
        if not isinstance(bg_cfg.get("default_schedule"), dict):
            errors.append("metadata.background.default_schedule must be an object")
    if not has_fg_cfg and not has_bg_cfg:
        process = meta.get("process")
        _validate_process_cfg(
            process,
            path="metadata.process",
            warnings=warnings,
            errors=errors,
        )
        if app_type == "ambient" and "default_schedule" in meta and not isinstance(meta.get("default_schedule"), dict):
            errors.append("metadata.default_schedule must be an object when provided")

    icon_file = meta.get("icon_file")
    if icon_file:
        icon_path = app_dir / str(icon_file)
        if not icon_path.exists():
            warnings.append(f"Icon file not found: {icon_file}")
    else:
        warnings.append("No icon specified in truffile.yaml")

    files_to_check: list[dict[str, Any]] = []
    raw_steps = config.get("steps", [])
    if raw_steps and not isinstance(raw_steps, list):
        errors.append("steps must be a list")
        raw_steps = []
    for idx, step in enumerate(raw_steps):
        if not isinstance(step, dict):
            errors.append(f"steps[{idx}] must be a mapping")
            continue
        step_type = step.get("type")
        step_label = step.get("name") or f"steps[{idx}]"
        if not isinstance(step_type, str) or not step_type.strip():
            errors.append(f"{step_label}: missing required field 'type'")
            continue
        step_type = step_type.strip().lower()
        if step_type in _UNSUPPORTED_STEP_HINTS:
            errors.append(f"{step_label}: {_UNSUPPORTED_STEP_HINTS[step_type]}")
            continue
        if step_type not in _SUPPORTED_STEP_TYPES:
            supported = ", ".join(sorted(_SUPPORTED_STEP_TYPES))
            errors.append(
                f"{step_label}: unknown step type '{step_type}' (supported: {supported})"
            )
            continue
        if step_type == "files":
            step_files = step.get("files", [])
            if isinstance(step_files, list):
                files_to_check.extend([f for f in step_files if isinstance(f, dict)])

    top_files = config.get("files", [])
    if isinstance(top_files, list):
        files_to_check.extend([f for f in top_files if isinstance(f, dict)])

    for f in files_to_check:
        source = f.get("source")
        if not isinstance(source, str):
            errors.append("files entries must include a string 'source'")
            continue

        src = app_dir / source
        if not src.exists():
            errors.append(f"Source file not found: {src}")
            continue

        if src.suffix == ".py":
            ok, err = _check_python_syntax(src)
            if not ok:
                errors.append(f"Syntax error in {src.name}: {err}")

    return len(errors) == 0, config, app_type, warnings, errors
