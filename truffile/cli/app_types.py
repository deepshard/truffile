from __future__ import annotations


def canonical_app_type(value: str | None) -> str:
    return {
        "focus": "foreground",
        "foreground": "foreground",
        "ambient": "background",
        "background": "background",
        "both": "hybrid",
        "foreground+background": "hybrid",
        "hybrid": "hybrid",
    }.get(str(value or "").lower(), "unknown")
