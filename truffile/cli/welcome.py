"""Rich welcome panels for chat, infer, and help."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .art import TRUFFLE_BANNER_BRAILLE, _color_top_row, _fg, ROYAL_BLUE, BOLD, DIM, RESET

_console = Console(highlight=False)

# colors matching C.CYAN (\033[96m)
ACCENT = "#56b6c2"
DIM_C = "#5a6a6e"
TEXT_C = "#d4d4d4"


def _braille_banner_rich() -> str:
    """Build the braille banner as a rich-markup string."""
    lines = TRUFFLE_BANNER_BRAILLE
    parts = []
    for i, line in enumerate(lines):
        if i <= 1:
            # top rows get colored but rich markup needs plain text — use raw ANSI
            parts.append(_color_top_row(line))
        else:
            parts.append(line)
    return "\n".join(parts)


def _build_panel(
    *,
    right_lines: list[str],
    title: str = "Truffile",
    subtitle: str = "",
) -> Panel:
    import shutil
    try:
        term_width = shutil.get_terminal_size().columns
    except Exception:
        term_width = 80

    right = Text.from_ansi("\n".join(right_lines))

    # two-column layout if terminal is wide enough for banner + commands
    if term_width >= 75:
        layout = Table.grid(padding=(0, 3))
        layout.add_column("left", justify="center")
        layout.add_column("right", justify="left")
        banner_text = _braille_banner_rich()
        left = Text.from_ansi(banner_text + f"\n\n  {_fg(*ROYAL_BLUE)}{BOLD}Truffile{RESET} {DIM}— Truffle SDK{RESET}")
        layout.add_row(left, right)
        content = layout
    else:
        # narrow terminal: commands only, no banner
        content = right

    return Panel(
        content,
        title=f"[bold {ACCENT}]{title}[/]",
        subtitle=f"[dim {DIM_C}]{subtitle}[/]" if subtitle else None,
        border_style=ACCENT,
        padding=(1, 2),
    )


def show_chat_welcome(*, device: str = "", apps: list[str] | None = None) -> None:
    """Welcome panel for truffile convo."""
    right: list[str] = []
    right.append(f"\033[1m\033[96mCommands\033[0m")
    cmds = [
        ("/help", "show commands"),
        ("/threads", "pick a thread"),
        ("/new", "new side thread"),
        ("/main", "switch to Main"),
        ("/history", "show history"),
        ("/rename <name>", "rename thread"),
        ("/apps", "list installed apps"),
        ("/exit", "exit Convo"),
    ]
    for name, desc in cmds:
        right.append(f"  \033[96m{name:<18}\033[0m \033[2m{desc}\033[0m")

    right.append("")
    right.append(f"\033[1m\033[96mKeys\033[0m")
    right.append(f"  \033[96m{'alt+enter':<18}\033[0m \033[2mnew line\033[0m")
    right.append(f"  \033[96m{'tab':<18}\033[0m \033[2mcomplete command\033[0m")
    right.append(f"  \033[96m{'esc/ctrl+c':<18}\033[0m \033[2minterrupt stream\033[0m")
    right.append(f"  \033[96m{'ctrl+d':<18}\033[0m \033[2mexit\033[0m")

    if apps:
        right.append("")
        right.append(f"\033[1m\033[96mApps\033[0m")
        for a in apps[:6]:
            right.append(f"  \033[96m/{a}\033[0m")
        if len(apps) > 6:
            right.append(f"  \033[2m...and {len(apps) - 6} more\033[0m")

    subtitle = f"connected to {device}" if device else ""
    _console.print(_build_panel(right_lines=right, title="Truffile Convo", subtitle=subtitle))


def show_infer_welcome(*, model: str = "", device: str = "") -> None:
    """Welcome panel for truffile infer."""
    right: list[str] = []
    right.append(f"\033[1m\033[96mCommands\033[0m")
    cmds = [
        ("/help", "show commands"),
        ("/models", "switch model"),
        ("/config", "show config"),
        ("/mcp connect <url>", "connect MCP"),
        ("/attach <path>", "attach image"),
        ("/create <name>", "scaffold new app"),
        ("/reset", "clear history"),
        ("/exit", "exit"),
    ]
    for name, desc in cmds:
        right.append(f"  \033[96m{name:<22}\033[0m \033[2m{desc}\033[0m")

    right.append("")
    right.append(f"\033[1m\033[96mKeys\033[0m")
    right.append(f"  \033[96m{'alt+enter':<22}\033[0m \033[2mnew line\033[0m")
    right.append(f"  \033[96m{'tab':<22}\033[0m \033[2mcomplete command\033[0m")
    right.append(f"  \033[96m{'esc':<22}\033[0m \033[2minterrupt stream\033[0m")
    right.append(f"  \033[96m{'ctrl+d':<22}\033[0m \033[2mexit\033[0m")

    if model:
        right.append("")
        right.append(f"\033[1m\033[96mModel\033[0m")
        right.append(f"  \033[2m{model}\033[0m")

    subtitle = f"{device} · {model}" if device and model else device or model or ""
    _console.print(_build_panel(right_lines=right, title="Truffile Infer", subtitle=subtitle))


def show_help_welcome() -> None:
    """Welcome panel for truffile help."""
    right: list[str] = []
    right.append(f"\033[1m\033[96mCommands\033[0m")
    cmds = [
        ("scan", "scan for devices"),
        ("connect <device>", "connect to device"),
        ("disconnect", "disconnect"),
        ("create [name]", "scaffold new app"),
        ("validate [path]", "validate app"),
        ("deploy [path]", "deploy to device"),
        ("list <apps|devices>", "list apps or devices"),
        ("delete [app]", "delete app"),
        ("users clear-other", "clear old users"),
        ("convo reset", "reset Convo"),
        ("models", "list models"),
        ("convo", "agent conversation"),
        ("infer", "raw inference"),
        ("help", "show this"),
    ]
    for name, desc in cmds:
        right.append(f"  \033[96m{name:<22}\033[0m \033[2m{desc}\033[0m")

    right.append("")
    right.append(f"\033[1m\033[96mExamples\033[0m")
    examples = [
        "truffile scan",
        "truffile connect truffle-1234",
        "truffile create my-app",
        "truffile deploy ./my-app",
        "truffile convo",
    ]
    for ex in examples:
        right.append(f"  \033[2m{ex}\033[0m")

    _console.print(_build_panel(right_lines=right, title="Truffile", subtitle="TruffleOS SDK"))
