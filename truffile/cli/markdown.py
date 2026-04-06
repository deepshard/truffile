from __future__ import annotations

import re
import shutil
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.theme import Theme


TRUFFILE_THEME = Theme({
    "markdown.h1": "bold #4169E1",
    "markdown.h2": "bold #4169E1",
    "markdown.h3": "#4169E1",
    "markdown.link": "#FF1493",
    "markdown.link_url": "dim #FF1493",
    "markdown.code": "#FFA500",
    "markdown.item.bullet": "#4169E1",
    "markdown.item.number": "#4169E1",
})

_console = Console(theme=TRUFFILE_THEME, highlight=False)

_MD_PATTERNS = [
    re.compile(r"```"),
    re.compile(r"^\s*#{1,6}\s", re.MULTILINE),
    re.compile(r"\*\*.+?\*\*"),
    re.compile(r"^\s*[-*+]\s", re.MULTILINE),
    re.compile(r"^\s*\d+\.\s", re.MULTILINE),
    re.compile(r"\[.+?\]\(.+?\)"),
]


def has_markdown(text: str) -> bool:
    for pattern in _MD_PATTERNS:
        if pattern.search(text):
            return True
    return False


def count_terminal_lines(text: str, terminal_width: int) -> int:
    lines = 0
    for line in text.split("\n"):
        visible_len = len(line)
        if visible_len == 0:
            lines += 1
        else:
            lines += max(1, (visible_len + terminal_width - 1) // terminal_width)
    return lines


def render_markdown(raw_text: str, lines_to_clear: int) -> None:
    if not raw_text.strip():
        return
    # move cursor up and clear each line of raw output
    for _ in range(lines_to_clear):
        sys.stdout.write("\033[A\033[K")
    sys.stdout.write("\033[K")
    sys.stdout.flush()
    _console.print(Markdown(raw_text))
