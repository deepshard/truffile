from __future__ import annotations

from typing import Any, Callable


async def handle_welcome(
    step: dict[str, Any],
    *,
    info: Callable[[str], None],
    non_interactive: bool = False,
    **_kw: Any,
) -> None:
    step_name = step.get("name", "Welcome")
    content = str(step.get("content", "") or "").strip()
    print()
    info(str(step_name))
    if content:
        print(content)
    if non_interactive:
        return
    input("  Press Enter to continue...")
