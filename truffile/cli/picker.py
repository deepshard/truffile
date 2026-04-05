from __future__ import annotations

from typing import Any

from .ui import C, DOT


def pick_from_list(
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
