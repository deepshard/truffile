from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


STATE_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def digest_hash(summary: str) -> str:
    return hashlib.sha256(summary.encode("utf-8")).hexdigest()


@dataclass
class BackgroundState:
    version: int = STATE_VERSION
    last_run_at: str = ""
    last_digest_at: str = ""
    last_digest_hash: str = ""
    last_stats: dict[str, Any] = field(default_factory=dict)
    page_fingerprints: dict[str, str] = field(default_factory=dict)


@dataclass
class LastDigest:
    generated_at: str
    digest_hash: str
    summary: str
    stats: dict[str, Any]
