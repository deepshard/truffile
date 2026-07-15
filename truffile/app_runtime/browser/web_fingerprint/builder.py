"""Build headers for outgoing requests using captured profiles."""

from __future__ import annotations

from typing import Dict, Optional

from .models import RequestProfile
from .sanitizer import sanitize_headers


class RequestProfileBuilder:
    """Merge base headers, captured profiles, and runtime overrides."""

    def __init__(self, transport: str = "browser"):
        self._transport = transport

    def build(
        self,
        base_headers: Optional[Dict[str, str]] = None,
        profile: Optional[RequestProfile] = None,
        runtime_headers: Optional[Dict[str, str]] = None,
        transport: Optional[str] = None,
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if base_headers:
            headers.update(base_headers)
        if profile:
            headers.update(profile.headers or {})
        if runtime_headers:
            headers.update(runtime_headers)

        transport_name = (transport or self._transport or "browser").lower()
        if transport_name not in {"browser", "playwright", "cdp"}:
            # non-browser transports often stand out if they include client hints
            drop = {
                "sec-ch-ua",
                "sec-ch-ua-platform",
                "sec-ch-ua-mobile",
                "sec-fetch-site",
                "sec-fetch-mode",
                "sec-fetch-dest",
                "sec-fetch-user",
                "priority",
            }
            return sanitize_headers(headers, drop_headers=drop)

        return sanitize_headers(headers)
