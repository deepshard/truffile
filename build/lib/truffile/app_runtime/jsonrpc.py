# shared JSON-RPC response parsing and httpx response adapter.
# used by apps that talk to remote MCP servers (arxiv, exa).

from __future__ import annotations

import json
from typing import Any

import httpx


def parse_jsonrpc_payload(raw: str) -> dict[str, Any] | None:
    """Parse a JSON-RPC response that may be plain JSON or SSE data: lines."""
    text = (raw or "").strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    candidate: dict[str, Any] | None = None
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except Exception:
            continue
        if isinstance(parsed, dict):
            candidate = parsed
    return candidate


class HttpxResponseAdapter:
    """Wraps httpx.Response to match the HttpResponse protocol."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    @property
    def status_code(self) -> int:
        return int(self._response.status_code)

    @property
    def is_success(self) -> bool:
        return bool(self._response.is_success)

    @property
    def text(self) -> str:
        return self._response.text

    @property
    def url(self) -> str:
        return str(self._response.url)

    def json(self) -> Any:
        return self._response.json()

    def raise_for_status(self) -> None:
        self._response.raise_for_status()
