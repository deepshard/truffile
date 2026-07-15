"""Utility helpers for request fingerprinting."""

from __future__ import annotations

from typing import Tuple
from urllib.parse import urlparse


def endpoint_key_from_request(method: str, url: str) -> Tuple[str, str, str, str]:
    """Return (endpoint_key, host, path, url_pattern).

    The endpoint_key is a stable identifier for a request: "METHOD host/path".
    url_pattern defaults to the exact path; callers can override for variable paths.
    """
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or "/"
    endpoint_key = f"{method.upper()} {host}{path}"
    return endpoint_key, host, path, path
