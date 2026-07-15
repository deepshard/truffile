from __future__ import annotations

from typing import Any


def ok(message: str, **data: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "success", "message": message}
    result.update(data)
    return result


def err(message: str, **data: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "error", "message": message}
    result.update(data)
    return result
