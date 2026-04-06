import json
import re
from importlib import resources as importlib_resources
from pathlib import Path

from .ui import C, ARROW, SCAFFOLD_ICON_RESOURCE_REL, error, success


def _safe_app_slug(app_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", app_name.lower()).strip("_")
    if not slug:
        return "my_app"
    if slug[0].isdigit():
        return f"app_{slug}"
    return slug


def _sample_truffile_yaml(app_name: str, slug: str) -> str:
    quoted_name = json.dumps(app_name)
    return (
        "metadata:\n"
        f"  name: {quoted_name}\n"
        f"  bundle_id: org.truffle.{slug.replace('_', '.')}\n"
        "  description: |\n"
        "    Describe what this app does.\n"
        "  icon_file: ./icon.png\n"
        "  foreground:\n"
        "    process:\n"
        "      cmd:\n"
        "        - python\n"
        f"        - {slug}_foreground.py\n"
        "      working_directory: /\n"
        "      environment:\n"
        '        PYTHONUNBUFFERED: "1"\n'
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
        "\n"
        "steps:\n"
        "  - name: Copy application files\n"
        "    type: files\n"
        "    files:\n"
        f"      - source: ./{slug}_foreground.py\n"
        f"        destination: ./{slug}_foreground.py\n"
        f"      - source: ./{slug}_background.py\n"
        f"        destination: ./{slug}_background.py\n"
    )


def _sample_foreground_py() -> str:
    return (
        '"""Foreground app entrypoint (MCP-facing surface)."""\n'
        "\n"
        "def main() -> None:\n"
        '    print(\"TODO: implement foreground MCP tool server\")\n'
        "\n"
        "\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n"
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
    app_name = (args.name or "").strip()
    if not app_name:
        try:
            app_name = input(f"{C.CYAN}?{C.RESET} App name: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
    if not app_name:
        error("App name is required")
        return 1
    if "/" in app_name or "\\" in app_name:
        error("App name cannot contain path separators")
        return 1

    base_dir: Path
    if args.path:
        base_dir = Path(args.path).expanduser().resolve()
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
        error(f"Target directory already exists: {app_dir}")
        return 1

    slug = _safe_app_slug(app_name)
    fg_file = f"{slug}_foreground.py"
    bg_file = f"{slug}_background.py"
    stock_icon_bytes, stock_icon_source = _load_stock_icon_bytes()
    if stock_icon_bytes is None:
        error(f"Stock icon not found: {stock_icon_source}")
        return 1
    if len(stock_icon_bytes) == 0:
        error(f"Stock icon is empty: {stock_icon_source}")
        return 1

    try:
        app_dir.mkdir(parents=True, exist_ok=False)
        (app_dir / "truffile.yaml").write_text(_sample_truffile_yaml(app_name, slug), encoding="utf-8")
        (app_dir / fg_file).write_text(_sample_foreground_py(), encoding="utf-8")
        (app_dir / bg_file).write_text(_sample_background_py(), encoding="utf-8")
        (app_dir / "icon.png").write_bytes(stock_icon_bytes)
    except Exception as exc:
        error(f"Failed to scaffold app: {exc}")
        return 1

    # OSC 8 clickable path (supported in iTerm2, VSCode, WezTerm, etc.)
    file_url = app_dir.as_uri()
    link = f"\x1b]8;;{file_url}\x1b\\{app_dir}\x1b]8;;\x1b\\"
    success(f"Created app scaffold: {link}")
    print(f"  {C.DIM}Files:{C.RESET}")
    print(f"  {C.DIM}{ARROW} truffile.yaml{C.RESET}")
    print(f"  {C.DIM}{ARROW} {fg_file}{C.RESET}")
    print(f"  {C.DIM}{ARROW} {bg_file}{C.RESET}")
    print(f"  {C.DIM}{ARROW} icon.png{C.RESET}")
    print()
    print(f"  {C.DIM}Next:{C.RESET} truffile validate {app_dir}")
    return 0
