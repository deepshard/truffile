"""Header sanitization utilities."""

from __future__ import annotations

from typing import Dict, Iterable, Optional

DEFAULT_DROP_HEADERS = {
    "content-length",
    "host",
    "cookie",
    "connection",
}


def sanitize_headers(
    headers: Dict[str, str],
    drop_headers: Optional[Iterable[str]] = None,
) -> Dict[str, str]:
    """Remove unsafe headers and normalize values."""
    drop = {h.lower() for h in (drop_headers or DEFAULT_DROP_HEADERS)}
    cleaned: Dict[str, str] = {}
    for key, value in headers.items():
        if value is None:
            continue
        if key.lower() in drop:
            continue
        cleaned[key] = str(value)
    return cleaned
