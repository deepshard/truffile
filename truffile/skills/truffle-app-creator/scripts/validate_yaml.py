#!/usr/bin/env python3
# validate truffile.yaml format and structure
# usage: python scripts/validate_yaml.py path/to/app/

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("install pyyaml: pip install pyyaml")
    sys.exit(1)

REQUIRED_METADATA = ["name", "bundle_id"]
VALID_STEP_TYPES = {"welcome", "bash", "files", "text", "oauth", "vnc"}
VALID_SCHEDULE_TYPES = {"interval", "times", "always"}


def validate(app_dir: Path) -> tuple[bool, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    truffile = app_dir / "truffile.yaml"
    if not truffile.exists():
        errors.append("truffile.yaml not found")
        return False, errors, warnings

    try:
        data = yaml.safe_load(truffile.read_text())
    except yaml.YAMLError as e:
        errors.append(f"yaml parse error: {e}")
        return False, errors, warnings

    if not isinstance(data, dict):
        errors.append("truffile.yaml must be a dict")
        return False, errors, warnings

    meta = data.get("metadata")
    if not isinstance(meta, dict):
        errors.append("metadata section missing or not a dict")
        return False, errors, warnings

    for field in REQUIRED_METADATA:
        if not meta.get(field):
            errors.append(f"metadata.{field} is required")

    has_fg = isinstance(meta.get("foreground"), dict)
    has_bg = isinstance(meta.get("background"), dict)
    if not has_fg and not has_bg:
        errors.append("must define foreground and/or background in metadata")

    if has_fg:
        fg = meta["foreground"]
        proc = fg.get("process")
        if not isinstance(proc, dict) or not proc.get("cmd"):
            errors.append("foreground.process.cmd is required")

    if has_bg:
        bg = meta["background"]
        proc = bg.get("process")
        if not isinstance(proc, dict) or not proc.get("cmd"):
            errors.append("background.process.cmd is required")
        schedule = bg.get("default_schedule")
        if not isinstance(schedule, dict):
            errors.append("background.default_schedule is required")
        elif schedule.get("type") not in VALID_SCHEDULE_TYPES:
            errors.append(f"invalid schedule type: {schedule.get('type')}. must be one of {VALID_SCHEDULE_TYPES}")

    icon_file = meta.get("icon_file")
    if icon_file:
        icon_path = app_dir / icon_file
        if not icon_path.exists():
            warnings.append(f"icon_file {icon_file} not found")
    else:
        warnings.append("no icon_file specified")

    steps = data.get("steps", [])
    if not isinstance(steps, list):
        errors.append("steps must be a list")
    else:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"step {i} is not a dict")
                continue
            step_type = step.get("type")
            if step_type not in VALID_STEP_TYPES:
                errors.append(f"step {i}: invalid type '{step_type}'")
            if step_type == "bash" and not step.get("run"):
                errors.append(f"step {i}: bash step missing 'run' field")
            if step_type == "files" and not step.get("files"):
                errors.append(f"step {i}: files step missing 'files' field")
            if step_type == "files":
                for f in step.get("files", []):
                    src = f.get("source", "")
                    if src:
                        src_path = app_dir / src
                        if not src_path.exists():
                            warnings.append(f"step {i}: source file not found: {src}")

    valid = len(errors) == 0
    return valid, errors, warnings


def main():
    parser = argparse.ArgumentParser(description="validate truffile.yaml")
    parser.add_argument("path", nargs="?", default=".", help="path to app directory")
    args = parser.parse_args()

    app_dir = Path(args.path).resolve()
    valid, errors, warnings = validate(app_dir)

    for w in warnings:
        print(f"  warning: {w}")
    for e in errors:
        print(f"  error: {e}")

    if valid:
        print(f"\n  valid: {app_dir / 'truffile.yaml'}")
    else:
        print(f"\n  invalid: {len(errors)} error(s)")
        sys.exit(1)


if __name__ == "__main__":
    main()
