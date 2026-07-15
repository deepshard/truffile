"""Data models for browser request fingerprints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class RequestProfile:
    """Captured browser request profile for a single endpoint."""

    endpoint_key: str
    method: str
    host: str
    path: str
    url_pattern: str
    headers: Dict[str, str] = field(default_factory=dict)
    captured_at: float = 0.0
    source: str = "sniffer"
    confidence: float = 1.0
    ttl_seconds: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "endpoint_key": self.endpoint_key,
            "method": self.method,
            "host": self.host,
            "path": self.path,
            "url_pattern": self.url_pattern,
            "headers": self.headers,
            "captured_at": self.captured_at,
            "source": self.source,
            "confidence": self.confidence,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "RequestProfile":
        headers = payload.get("headers")
        return cls(
            endpoint_key=str(payload.get("endpoint_key", "")),
            method=str(payload.get("method", "")),
            host=str(payload.get("host", "")),
            path=str(payload.get("path", "")),
            url_pattern=str(payload.get("url_pattern", "")),
            headers=headers if isinstance(headers, dict) else {},
            captured_at=float(payload.get("captured_at", 0.0) or 0.0),
            source=str(payload.get("source", "sniffer")),
            confidence=float(payload.get("confidence", 1.0) or 1.0),
            ttl_seconds=payload.get("ttl_seconds")
            if payload.get("ttl_seconds") is None
            else int(payload.get("ttl_seconds")),
        )
