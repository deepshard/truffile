from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class FileTokenStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict[str, Any] | None:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(self._path, 0o600)
        except Exception:
            pass

    def delete(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except Exception:
            pass


class MemoryTokenStore:
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data = dict(initial) if initial is not None else None

    def load(self) -> dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None

    def save(self, data: dict[str, Any]) -> None:
        self._data = dict(data)

    def delete(self) -> None:
        self._data = None


class FileCookieStore:
    def __init__(self, cookies_path: str | Path, metadata_path: str | Path) -> None:
        self._cookies_path = Path(cookies_path)
        self._metadata_path = Path(metadata_path)

    def load_cookies(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._cookies_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self._cookies_path.parent.mkdir(parents=True, exist_ok=True)
        self._cookies_path.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
        try:
            os.chmod(self._cookies_path, 0o600)
        except Exception:
            pass

    def load_metadata(self) -> dict[str, Any] | None:
        try:
            data = json.loads(self._metadata_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def save_metadata(self, data: dict[str, Any]) -> None:
        self._metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._metadata_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(self._metadata_path, 0o600)
        except Exception:
            pass

    def clear(self) -> None:
        for path in (self._cookies_path, self._metadata_path):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass


class MemoryCookieStore:
    def __init__(self) -> None:
        self._cookies: list[dict[str, Any]] = []
        self._metadata: dict[str, Any] | None = None

    def load_cookies(self) -> list[dict[str, Any]]:
        return list(self._cookies)

    def save_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self._cookies = list(cookies)

    def load_metadata(self) -> dict[str, Any] | None:
        return dict(self._metadata) if self._metadata is not None else None

    def save_metadata(self, data: dict[str, Any]) -> None:
        self._metadata = dict(data)

    def clear(self) -> None:
        self._cookies.clear()
        self._metadata = None
