from pathlib import Path

from truffile.schema import validate_app_dir

from .app_types import canonical_app_type
from .output import emit_error, emit_json, ok_payload
from .ui import C, error, warn, info, success


def cmd_validate(args) -> int:
    json_out = bool(getattr(args, "json", False))
    app_dir = Path(args.path).resolve()
    if not app_dir.exists() or not app_dir.is_dir():
        if json_out:
            return emit_error("invalid_path", f"{app_dir} is not a valid directory")
        error(f"{app_dir} is not a valid directory")
        return 1

    if not json_out:
        info(f"Validating app in {app_dir.name}")
    valid, _config, app_type, warnings, errors = validate_app_dir(app_dir)
    if json_out:
        if not valid:
            return emit_error(
                "validation_failed",
                "App validation failed",
                path=str(app_dir),
                warnings=warnings,
                errors=errors,
            )
        emit_json(ok_payload(
            path=str(app_dir),
            type=canonical_app_type(app_type),
            app_type=app_type,
            warnings=warnings,
        ))
        return 0

    for w in warnings:
        warn(w)
    if not valid:
        for e in errors:
            error(e)
        return 1

    success(f"Validation passed ({app_type})")
    return 0
