from __future__ import annotations

import sys
from typing import Any

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style

from .ui import C


PICKER_STYLE = Style.from_dict({
    "selected": "#4169E1 bold",
    "label": "",
    "detail": "#666666",
    "current": "#22c55e",
    "pointer": "#4169E1 bold",
})


async def pick_from_list(
    items: list[dict[str, Any]],
    *,
    label_key: str = "label",
    detail_key: str = "detail",
    active_key: str | None = None,
    active_value: Any = None,
    prompt: str = "pick one",
) -> dict[str, Any] | None:
    if not items:
        return None

    # fallback for non-tty
    if not sys.stdout.isatty():
        return _fallback_pick(items, label_key=label_key, detail_key=detail_key,
                              active_key=active_key, active_value=active_value, prompt=prompt)

    selected_idx = [0]
    result: list[dict[str, Any] | None] = [None]

    def _get_text():
        fragments: list[tuple[str, str]] = []
        fragments.append(("class:detail", f"  {prompt} (↑↓ enter esc)\n"))
        for i, item in enumerate(items):
            label = item.get(label_key, "?")
            detail = item.get(detail_key, "")
            is_active = active_key and item.get(active_key) == active_value
            is_selected = i == selected_idx[0]

            if is_selected:
                fragments.append(("class:pointer", "  › "))
                fragments.append(("class:selected", label))
            else:
                fragments.append(("", "    "))
                fragments.append(("class:label", label))

            if is_active:
                fragments.append(("class:current", " (current)"))
            if detail:
                fragments.append(("class:detail", f" {detail}"))
            fragments.append(("", "\n"))
        return FormattedText(fragments)

    kb = KeyBindings()

    @kb.add("up")
    def _up(event):
        selected_idx[0] = (selected_idx[0] - 1) % len(items)

    @kb.add("down")
    def _down(event):
        selected_idx[0] = (selected_idx[0] + 1) % len(items)

    @kb.add("enter")
    def _enter(event):
        result[0] = items[selected_idx[0]]
        event.app.exit()

    @kb.add("escape")
    def _escape(event):
        result[0] = None
        event.app.exit()

    @kb.add("c-c")
    def _ctrlc(event):
        result[0] = None
        event.app.exit()

    @kb.add("c-d")
    def _ctrld(event):
        result[0] = None
        event.app.exit()

    layout = Layout(HSplit([Window(FormattedTextControl(_get_text))]))
    app = Application(layout=layout, key_bindings=kb, style=PICKER_STYLE, full_screen=False)

    try:
        await app.run_async()
    except (EOFError, KeyboardInterrupt):
        return None

    return result[0]


def _fallback_pick(
    items: list[dict[str, Any]],
    *,
    label_key: str = "label",
    detail_key: str = "detail",
    active_key: str | None = None,
    active_value: Any = None,
    prompt: str = "pick one",
) -> dict[str, Any] | None:
    """Simple numbered fallback for non-interactive terminals."""
    print()
    for i, item in enumerate(items, 1):
        label = item.get(label_key, "?")
        detail = item.get(detail_key, "")
        is_active = active_key and item.get(active_key) == active_value
        line = f"  {C.CYAN}{i}.{C.RESET} {label}"
        if is_active:
            line += f" {C.GREEN}(current){C.RESET}"
        if detail:
            line += f" {C.DIM}{detail}{C.RESET}"
        print(line)
    print()
    try:
        choice = input(f"{prompt} (1-{len(items)}) or enter to cancel: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not choice:
        return None
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(items):
            return items[idx]
    except ValueError:
        pass
    return None
