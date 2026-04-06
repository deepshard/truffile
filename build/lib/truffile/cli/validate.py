from pathlib import Path

from truffile.schema import validate_app_dir

from .ui import C, error, warn, info, success


def cmd_validate(args) -> int:
    app_dir = Path(args.path).resolve()
    if not app_dir.exists() or not app_dir.is_dir():
        error(f"{app_dir} is not a valid directory")
        return 1

    info(f"Validating app in {app_dir.name}")
    valid, _config, app_type, warnings, errors = validate_app_dir(app_dir)
    for w in warnings:
        warn(w)
    if not valid:
        for e in errors:
            error(e)
        return 1

    success(f"Validation passed ({app_type})")
    return 0
