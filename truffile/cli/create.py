import json
import re
from importlib import resources as importlib_resources
from pathlib import Path

from .output import emit_error, emit_json, ok_payload
from .ui import C, ARROW, SCAFFOLD_ICON_RESOURCE_REL, error, success


APP_TYPES = ("foreground", "background", "hybrid")


def _safe_app_slug(app_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", app_name.lower()).strip("_")
    if not slug:
        return "my_app"
    if slug[0].isdigit():
        return f"app_{slug}"
    return slug


def _sample_truffile_yaml(app_name: str, slug: str, app_type: str = "hybrid") -> str:
    if app_type not in APP_TYPES:
        raise ValueError(f"Unsupported app type: {app_type}")
    quoted_name = json.dumps(app_name)
    has_foreground = app_type != "background"
    has_background = app_type != "foreground"
    foreground = (
        "  foreground:\n"
        "    process:\n"
        "      cmd:\n"
        "        - python\n"
        f"        - {slug}_foreground.py\n"
        "      working_directory: /\n"
        "      environment:\n"
        '        PYTHONUNBUFFERED: "1"\n'
        if has_foreground
        else ""
    )
    background = (
        "  background:\n"
        "    process:\n"
        "      cmd:\n"
        "        - python\n"
        f"        - {slug}_background.py\n"
        "      working_directory: /\n"
        "      environment:\n"
        '        PYTHONUNBUFFERED: "1"\n'
        "    default_schedule:\n"
        "      type: interval\n"
        "      interval:\n"
        "        duration: 30m\n"
        "        schedule:\n"
        '          daily_window: "00:00-23:59"\n'
        if has_background
        else ""
    )
    app_files = []
    if has_foreground:
        app_files.append(f"{slug}_foreground.py")
    if has_background:
        app_files.append(f"{slug}_background.py")
    file_steps = "".join(
        f"      - source: ./{filename}\n"
        f"        destination: ./{filename}\n"
        for filename in app_files
    )
    return (
        "metadata:\n"
        f"  name: {quoted_name}\n"
        f"  bundle_id: org.truffle.{slug.replace('_', '.')}\n"
        "  description: |\n"
        "    Describe what this app does.\n"
        "  icon_file: ./icon.png\n"
        f"{foreground}"
        f"{background}"
        "\n"
        "steps:\n"
        "  - name: Copy application files\n"
        "    type: files\n"
        "    files:\n"
        f"{file_steps}"
    )


def _sample_foreground_py(app_name: str, slug: str) -> str:
    app_name_json = json.dumps(app_name)
    return (
        '"""Foreground app entrypoint (MCP-facing surface)."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "from truffile.app_runtime import ForegroundApp, ToolSpec\n"
        "\n"
        "\n"
        f"app = ForegroundApp({app_name_json})\n"
        "\n"
        "\n"
        "@app.tool(\n"
        "    ToolSpec(\n"
        f"        name=\"{slug}_ping\",\n"
        "        description=\"Return a small pong payload for smoke testing this app.\",\n"
        "        icon=\"check-circle\",\n"
        "        annotations={\"readOnlyHint\": True, \"destructiveHint\": False},\n"
        "    )\n"
        ")\n"
        f"async def {slug}_ping(message: str = \"pong\") -> dict:\n"
        "    return {\"status\": \"ok\", \"message\": message}\n"
        "\n"
        "\n"
        "if __name__ == \"__main__\":\n"
        "    app.run()\n"
    )


def _sample_background_py() -> str:
    return (
        '"""Background app entrypoint (scheduled context emitter)."""\n'
        "\n"
        "def main() -> None:\n"
        '    print(\"TODO: implement background scheduled job\")\n'
        "\n"
        "\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n"
    )


def _load_stock_icon_bytes() -> tuple[bytes | None, str]:
    try:
        resource_file = importlib_resources.files("truffile").joinpath(str(SCAFFOLD_ICON_RESOURCE_REL))
        icon_bytes = resource_file.read_bytes()
        return icon_bytes, f"truffile/{SCAFFOLD_ICON_RESOURCE_REL.as_posix()}"
    except Exception:
        pass

    local_package_path = Path(__file__).resolve().parent.parent / SCAFFOLD_ICON_RESOURCE_REL
    if local_package_path.exists() and local_package_path.is_file():
        return local_package_path.read_bytes(), str(local_package_path)

    legacy_docs_path = Path(__file__).resolve().parents[2] / "docs" / "Truffle.png"
    if legacy_docs_path.exists() and legacy_docs_path.is_file():
        return legacy_docs_path.read_bytes(), str(legacy_docs_path)

    return None, f"truffile/{SCAFFOLD_ICON_RESOURCE_REL.as_posix()}"


def cmd_create(args) -> int:
    json_out = bool(getattr(args, "json", False))
    non_interactive = bool(getattr(args, "non_interactive", False)) or json_out

    def fail(code: str, message: str) -> int:
        if json_out:
            return emit_error(code, message)
        error(message)
        return 1

    app_type = getattr(args, "app_type", "hybrid")
    if app_type not in APP_TYPES:
        return fail("invalid_type", f"App type must be one of: {', '.join(APP_TYPES)}")
    has_foreground = app_type != "background"
    has_background = app_type != "foreground"

    app_name = (args.name or "").strip()
    if not app_name:
        if non_interactive:
            return fail("input_required", "App name is required")
        try:
            app_name = input(f"{C.CYAN}?{C.RESET} App name: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
    if not app_name:
        return fail("input_required", "App name is required")
    if "/" in app_name or "\\" in app_name:
        return fail("invalid_name", "App name cannot contain path separators")

    base_dir: Path
    if args.path:
        base_dir = Path(args.path).expanduser().resolve()
    elif non_interactive:
        base_dir = Path.cwd()
    else:
        cwd = Path.cwd()
        try:
            raw = input(f"{C.CYAN}?{C.RESET} Base path [{cwd}]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
        base_dir = Path(raw).expanduser().resolve() if raw else cwd

    app_dir = base_dir / app_name
    if app_dir.exists():
        if json_out:
            return emit_error(
                "target_exists",
                f"Target directory already exists: {app_dir}",
                next_action="Choose a different app name or base path.",
            )
        return fail("target_exists", f"Target directory already exists: {app_dir}")

    slug = _safe_app_slug(app_name)
    fg_file = f"{slug}_foreground.py"
    bg_file = f"{slug}_background.py"
    stock_icon_bytes, stock_icon_source = _load_stock_icon_bytes()
    if stock_icon_bytes is None:
        return fail("stock_icon_missing", f"Stock icon not found: {stock_icon_source}")
    if len(stock_icon_bytes) == 0:
        return fail("stock_icon_empty", f"Stock icon is empty: {stock_icon_source}")

    try:
        app_dir.mkdir(parents=True, exist_ok=False)
        (app_dir / "truffile.yaml").write_text(
            _sample_truffile_yaml(app_name, slug, app_type),
            encoding="utf-8",
        )
        if has_foreground:
            (app_dir / fg_file).write_text(_sample_foreground_py(app_name, slug), encoding="utf-8")
        if has_background:
            (app_dir / bg_file).write_text(_sample_background_py(), encoding="utf-8")
        (app_dir / "icon.png").write_bytes(stock_icon_bytes)
    except Exception as exc:
        return fail("create_failed", f"Failed to scaffold app: {exc}")

    files = ["truffile.yaml"]
    if has_foreground:
        files.append(fg_file)
    if has_background:
        files.append(bg_file)
    files.append("icon.png")
    if json_out:
        emit_json(ok_payload(
            app={"name": app_name, "slug": slug, "type": app_type, "path": str(app_dir)},
            files=files,
            next_action=f"truffile validate {app_dir} --json",
        ))
        return 0

    # OSC 8 clickable path (supported in iTerm2, VSCode, WezTerm, etc.)
    file_url = app_dir.as_uri()
    link = f"\x1b]8;;{file_url}\a{app_dir}\x1b]8;;\a"
    success(f"Created app scaffold: {link}")
    print(f"  {C.DIM}Files:{C.RESET}")
    for filename in files:
        print(f"  {C.DIM}{ARROW} {filename}{C.RESET}")
    print()
    print(f"  {C.DIM}Next:{C.RESET} truffile validate {app_dir}")
    return 0
