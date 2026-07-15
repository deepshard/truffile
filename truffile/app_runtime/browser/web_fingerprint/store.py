"""Persistence for request profiles."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Iterable, Optional

from .models import RequestProfile


class RequestProfileStore:
    """Store and load request profiles from disk."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._profiles: Dict[str, RequestProfile] = {}
        self._loaded = False

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        if self._loaded:
            return
        if not self._path.exists():
            self._loaded = True
            return
        try:
            payload = json.loads(self._path.read_text())
        except Exception:
            self._loaded = True
            return

        profiles = payload.get("profiles") if isinstance(payload, dict) else None
        if isinstance(profiles, list):
            for item in profiles:
                if isinstance(item, dict):
                    profile = RequestProfile.from_dict(item)
                    if profile.endpoint_key:
                        self._profiles[profile.endpoint_key] = profile
        self._loaded = True

    def save(self) -> None:
        data = {
            "saved_at": time.time(),
            "profiles": [profile.to_dict() for profile in self._profiles.values()],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2))

    def upsert(self, profile: RequestProfile) -> None:
        self._profiles[profile.endpoint_key] = profile

    def get(self, endpoint_key: str) -> Optional[RequestProfile]:
        return self._profiles.get(endpoint_key)

    def all(self) -> Iterable[RequestProfile]:
        return list(self._profiles.values())

    def prune_expired(self, now: Optional[float] = None) -> None:
        now = now or time.time()
        expired = []
        for key, profile in self._profiles.items():
            ttl = profile.ttl_seconds
            if ttl is not None and profile.captured_at and now - profile.captured_at > ttl:
                expired.append(key)
        for key in expired:
            self._profiles.pop(key, None)
