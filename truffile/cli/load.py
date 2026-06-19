from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path
from typing import Iterable

from .ui import C, ARROW, error, success, warn


RESOURCE_MAP = {
    "skills": ("skills", Path("truffile") / "skills"),
    "examples": ("app-store", Path("truffile") / "examples"),
}


def _ignore_generated(_dir: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", ".pytest_cache"}
    return {name for name in names if name in ignored or name.endswith(".pyc")}


def _copy_resource_tree(resource_name: str, destination: Path, *, force: bool) -> int:
    source = resources.files("truffile").joinpath(resource_name)
    if not source.is_dir():
        raise FileNotFoundError(f"bundled resource not found: truffile/{resource_name}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not force:
            warn(f"Skipping existing {destination}; pass --force to replace it")
            return 0
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    with resources.as_file(source) as source_path:
        shutil.copytree(source_path, destination, ignore=_ignore_generated)
    return 1


def _targets(selection: str) -> Iterable[tuple[str, str, Path]]:
    if selection == "all":
        for name, (resource_name, rel_dest) in RESOURCE_MAP.items():
            yield name, resource_name, rel_dest
        return
    resource_name, rel_dest = RESOURCE_MAP[selection]
    yield selection, resource_name, rel_dest


def cmd_load(args) -> int:
    selection = getattr(args, "what", "all")
    base = Path(getattr(args, "path", ".") or ".").expanduser().resolve()
    force = bool(getattr(args, "force", False))
    json_out = bool(getattr(args, "json", False))

    results: list[dict[str, str | bool]] = []
    try:
        for label, resource_name, rel_dest in _targets(selection):
            dest = base / rel_dest
            copied = bool(_copy_resource_tree(resource_name, dest, force=force))
            results.append({
                "name": label,
                "path": str(dest),
                "copied": copied,
            })
    except Exception as exc:
        if json_out:
            print(json.dumps({"status": "error", "message": str(exc)}, indent=2))
        else:
            error(str(exc))
        return 1

    if json_out:
        print(json.dumps({"status": "ok", "resources": results}, indent=2))
        return 0

    for result in results:
        label = result["name"]
        dest = result["path"]
        if result["copied"]:
            success(f"Loaded {label}: {dest}")
        else:
            print(f"  {C.DIM}{ARROW} {label}: {dest}{C.RESET}")
    return 0
