from pathlib import Path

from truffile.schema import validate_app_dir

from .ui import C, error, warn, info, success


def cmd_validate(args) -> int:
    app_dir = Path(args.path).resolve()
    if not getattr(args, "legacy_builder", False):
        from truffile.deploy.native import prepare_bundle
        try:
            with prepare_bundle(app_dir) as bundle:
                success(f"Bundle preflight passed: {bundle.config['metadata']['name']}")
                info("Firmware validates the full manifest and install plan during deployment.")
                return 0
        except Exception as exc:
            error(str(exc))
            return 1
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
