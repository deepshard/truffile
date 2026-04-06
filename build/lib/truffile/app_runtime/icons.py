from __future__ import annotations

PHOSPHOR_ICON_BASE_URL = "https://raw.githubusercontent.com/phosphor-icons/core/main/assets/regular"


def phosphor_icon_url(name: str) -> str:
    slug = str(name or "").strip()
    if not slug:
        raise ValueError("icon name must be non-empty")
    return f"{PHOSPHOR_ICON_BASE_URL}/{slug}.svg"
