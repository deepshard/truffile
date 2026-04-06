"""handy utilities for managing tool result size in foreground and background apps.

app can use these as helpers to avoid facing runtimes chopping block
"""

from __future__ import annotations

import json
import logging
from typing import Any, Sequence

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 80_000


def truncate_result(text: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Hard-truncate a text result with an informative suffix."""
    if len(text) <= max_chars:
        return text
    original_len = len(text)
    logger.warning(
        "Tool result is %s chars (limit: %s). Truncating.",
        f"{original_len:,}",
        f"{max_chars:,}",
    )
    return (
        text[:max_chars]
        + f"\n\n[Result truncated: original was {original_len:,} chars, "
        f"showing first {max_chars:,}. Narrow your query for more specific results.]"
    )


def truncate_items(
    items: Sequence[Any],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    serialize: Any | None = None,
) -> str:
    """Serialize a list of items and drop trailing items that exceed the budget.

    Unlike ``truncate_result`` which chops mid-text, this drops whole items so
    the output stays valid (no half-JSON or broken CSV rows).

    ``serialize`` is an optional callable ``(item) -> str``.  Defaults to
    ``json.dumps``.
    """
    if serialize is None:
        serialize = lambda item: json.dumps(item, ensure_ascii=False)

    parts: list[str] = []
    used = 0
    kept = 0

    for item in items:
        chunk = serialize(item)
        if used + len(chunk) > max_chars and parts:
            break
        parts.append(chunk)
        used += len(chunk)
        kept += 1

    dropped = len(items) - kept
    body = "\n".join(parts)

    if dropped > 0:
        logger.warning(
            "Dropped %d of %d items to stay within %s char limit.",
            dropped,
            len(items),
            f"{max_chars:,}",
        )
        body += (
            f"\n\n[Showing {kept} of {len(items)} items. "
            f"{dropped} items dropped to stay within size limit. "
            f"Narrow your query for more specific results.]"
        )

    return body
