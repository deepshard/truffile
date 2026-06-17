#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[1]
RESOURCES_ROOT = REPO_ROOT / "truffile" / "resources"
APP_STORE_ROOT = RESOURCES_ROOT / "app-store"
INDEX_PATH = RESOURCES_ROOT / "index.json"
REMOTE_MCP_MARKERS = (
    "remote_mcp",
    "RemoteMcp",
    "RemoteMCP",
    "streamablehttp_client",
)
TEXT_EXTENSIONS = {
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
}
SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
SKIP_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the packaged truffile resource index.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if truffile/resources/index.json is missing or stale.",
    )
    args = parser.parse_args()

    rendered = json.dumps(build_index(), indent=2, sort_keys=True) + "\n"
    if args.check:
        existing = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
        if existing != rendered:
            print(f"{INDEX_PATH.relative_to(REPO_ROOT)} is stale; run {SCRIPT_PATH.relative_to(REPO_ROOT)}")
            return 1
        return 0

    INDEX_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {INDEX_PATH.relative_to(REPO_ROOT)}")
    return 0


def build_index() -> dict[str, Any]:
    return {
        "generated_by": str(SCRIPT_PATH.relative_to(REPO_ROOT)),
        "resources": [_build_app_example_entry(app_dir) for app_dir in _iter_app_dirs()],
        "version": 1,
    }


def _iter_app_dirs() -> list[Path]:
    if not APP_STORE_ROOT.exists():
        return []
    return sorted(
        app_dir
        for app_dir in APP_STORE_ROOT.iterdir()
        if app_dir.is_dir() and (app_dir / "truffile.yaml").is_file()
    )


def _build_app_example_entry(app_dir: Path) -> dict[str, Any]:
    slug = app_dir.name
    manifest = _read_yaml(app_dir / "truffile.yaml")
    metadata = _as_dict(manifest.get("metadata"))
    steps = [_as_dict(step) for step in _as_list(manifest.get("steps"))]
    step_types = sorted({str(step.get("type", "")).strip() for step in steps if step.get("type")})
    files = _list_files(app_dir)
    app_kind = _app_kind(metadata)
    tags = _build_tags(app_dir, app_kind=app_kind, step_types=step_types)
    title = str(metadata.get("name") or slug)
    description = _one_line(metadata.get("description"))

    return {
        "files": files,
        "id": f"app-store.{slug}",
        "kind": "app_example",
        "metadata": {
            "app_kind": app_kind,
            "bundle_id": str(metadata.get("bundle_id") or ""),
            "slug": slug,
            "step_types": step_types,
        },
        "path": str(app_dir.relative_to(RESOURCES_ROOT)),
        "summary": description,
        "tags": tags,
        "title": title,
    }


def _read_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _as_dict(raw)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _one_line(value: Any) -> str:
    return " ".join(str(value or "").split())


def _app_kind(metadata: dict[str, Any]) -> str:
    has_foreground = bool(metadata.get("foreground"))
    has_background = bool(metadata.get("background"))
    if has_foreground and has_background:
        return "fg+bg"
    if has_foreground:
        return "fg"
    if has_background:
        return "bg"
    return "unknown"


def _build_tags(app_dir: Path, *, app_kind: str, step_types: list[str]) -> list[str]:
    tags = set(step_types)
    if "oauth" in tags:
        tags.add("oauth_app")
    if "text" in tags:
        tags.add("text_config_app")
    if "vnc" in tags:
        tags.add("browser_vnc_app")
    if "oauth" not in tags and "text" not in tags and "vnc" not in tags:
        tags.add("no_auth_app")

    match app_kind:
        case "fg+bg":
            tags.add("foreground_background")
        case "fg":
            tags.add("foreground_only")
        case "bg":
            tags.add("background_only")

    if _uses_remote_mcp(app_dir):
        tags.add("remote_mcp")
    if (app_dir / "tests").is_dir():
        tags.add("tests")

    return sorted(tags)


def _uses_remote_mcp(app_dir: Path) -> bool:
    for path in _walk_files(app_dir):
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = text.lower()
        if any(marker in text for marker in REMOTE_MCP_MARKERS):
            return True
        if "https://" in lowered and "/mcp" in lowered:
            return True
    return False


def _list_files(app_dir: Path) -> list[str]:
    return sorted(str(path.relative_to(app_dir)) for path in _walk_files(app_dir))


def _walk_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        if path.suffix in SKIP_FILE_SUFFIXES:
            continue
        files.append(path)
    return files


if __name__ == "__main__":
    sys.exit(main())
