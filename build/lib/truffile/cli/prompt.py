from __future__ import annotations

import shutil
import time

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from .commands import SlashCommand


TRUFFILE_STYLE = Style.from_dict({
    "prompt": "#56b6c2 bold",
    "continuation": "#666666",
    "bottom-toolbar": "noreverse #555555",
    "bottom-toolbar.text": "noreverse #555555",
    # dropdown
    "completion-menu.completion": "bg:#2a2a2a #56b6c2",
    "completion-menu.completion.current": "bg:#3a3a4a #56b6c2 bold",
    "completion-menu.meta.completion": "bg:#2a2a2a #888888",
    "completion-menu.meta.completion.current": "bg:#3a3a4a #bbbbbb",
    "scrollbar.background": "bg:#2a2a2a",
    "scrollbar.button": "bg:#56b6c2",
})

# thin horizontal rule using ANSI bright cyan (\033[96m) to match C.CYAN
_CYAN = "\033[96m"
_DIM = "\033[2m"
_RESET = "\033[0m"


class SlashCommandCompleter(Completer):
    def __init__(self, commands: list[SlashCommand]):
        self.commands = list(commands)

    def add_commands(self, commands: list[SlashCommand]) -> None:
        for cmd in commands:
            if not any(c.name == cmd.name for c in self.commands):
                self.commands.append(cmd)

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor.lstrip()
        if not text.startswith("/"):
            return

        parts = text.split(maxsplit=1)
        if len(parts) > 1:
            return

        prefix = parts[0].lower()
        for cmd in self.commands:
            if not cmd.name.lower().startswith(prefix):
                continue
            display = f"{cmd.name} {cmd.arg_hint}" if cmd.arg_hint else cmd.name
            yield Completion(
                cmd.name,
                start_position=-len(prefix),
                display=display,
                display_meta=cmd.description,
            )


def _build_keybindings() -> KeyBindings:
    kb = KeyBindings()

    @kb.add("enter", eager=True)
    def _submit(event):
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def _newline_alt_enter(event):
        event.current_buffer.insert_text("\n")

    @kb.add("c-j")
    def _newline_ctrl_j(event):
        event.current_buffer.insert_text("\n")

    return kb


def _hr(task_name: str = "") -> str:
    """Thin horizontal rule, optional right-aligned task name."""
    try:
        width = shutil.get_terminal_size().columns
    except Exception:
        width = 80
    if task_name:
        label = f" {task_name} "
        line_len = max(0, width - len(label))
        return "─" * line_len + label
    return "─" * width


class TrufflePrompt:
    """Shared input component for chat and infer REPLs."""

    def __init__(self, prompt_text: str, commands: list[SlashCommand]):
        self._completer = SlashCommandCompleter(commands)
        self._session = PromptSession(
            completer=self._completer,
            key_bindings=_build_keybindings(),
            multiline=True,
            prompt_continuation=self._continuation,
            style=TRUFFILE_STYLE,
            complete_while_typing=True,
        )
        self._prompt_text = prompt_text
        self._ctrlc_time: float | None = None
        self.task_name: str = ""

    def add_commands(self, commands: list[SlashCommand]) -> None:
        self._completer.add_commands(commands)

    @staticmethod
    def _continuation(width: int, line_number: int, wrap_count: int) -> str:
        return "." * (width - 1) + " "

    def _bottom_toolbar(self) -> FormattedText:
        line = _hr(self.task_name)
        return FormattedText([("", line)])

    async def get_input(self) -> str | None:
        """Returns user text, empty string on single Ctrl+C, None on exit."""
        try:
            text = await self._session.prompt_async(
                HTML(f"<prompt>{self._prompt_text}</prompt>"),
                bottom_toolbar=self._bottom_toolbar,
            )
            self._ctrlc_time = None
            return text
        except EOFError:
            return None
        except KeyboardInterrupt:
            return self._handle_ctrlc()

    def _handle_ctrlc(self) -> str | None:
        now = time.monotonic()
        if self._ctrlc_time is not None and (now - self._ctrlc_time) < 3.0:
            return None
        self._ctrlc_time = now
        print("\npress ctrl+c again to quit (or ctrl+d)")
        return ""
