"""Match request profiles to outgoing API calls."""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from .models import RequestProfile
from .store import RequestProfileStore
from .utils import endpoint_key_from_request


class RequestProfileMatcher:
    """Find the best request profile for a given API call."""

    def __init__(self, store: RequestProfileStore):
        self._store = store

    def match(
        self,
        method: str,
        url: str,
        endpoint_key: Optional[str] = None,
    ) -> Optional[RequestProfile]:
        if endpoint_key:
            profile = self._store.get(endpoint_key)
            if profile:
                return profile

        computed_key, host, path, _ = endpoint_key_from_request(method, url)
        profile = self._store.get(computed_key)
        if profile:
            return profile

        parsed = urlparse(url)
        host = parsed.netloc
        path = parsed.path or "/"
        best_profile = None
        best_len = -1
        for candidate in self._store.all():
            if candidate.method != method.upper():
                continue
            if candidate.host != host:
                continue
            prefix = candidate.url_pattern or candidate.path
            if prefix and path.startswith(prefix) and len(prefix) > best_len:
                best_profile = candidate
                best_len = len(prefix)
        return best_profile
