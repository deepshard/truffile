from __future__ import annotations

from typing import Any, Callable


async def handle_welcome(
    step: dict[str, Any],
    *,
    info: Callable[[str], None],
    **_kw: Any,
) -> None:
    step_name = step.get("name", "Welcome")
    content = str(step.get("content", "") or "").strip()
    print()
    info(str(step_name))
    if content:
        print(content)
    input("  Press Enter to continue...")
