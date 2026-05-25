"""Configuration helpers for the WHOOP Truffle app."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_WHOOP_API_BASE = "https://api.prod.whoop.com/developer"
DEFAULT_WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
DEFAULT_TOKEN_STORE_PATH = Path.home() / ".whoop-truffle" / "oauth.json"


def _parse_optional_float(raw: str | None) -> float | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class WhoopConfig:
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    access_token: str = ""
    refresh_token: str = ""
    api_base: str = DEFAULT_WHOOP_API_BASE
    token_url: str = DEFAULT_WHOOP_TOKEN_URL
    token_store_path: Path = DEFAULT_TOKEN_STORE_PATH
    access_token_expires_at: float | None = None
    token_scope: str = ""
    token_type: str = "bearer"

    @classmethod
    def from_env(cls) -> WhoopConfig:
        token_store_raw = os.getenv("WHOOP_TOKEN_STORE_PATH", "").strip()
        token_store_path = Path(token_store_raw) if token_store_raw else DEFAULT_TOKEN_STORE_PATH
        return cls(
            client_id=os.getenv("WHOOP_CLIENT_ID", "").strip(),
            client_secret=os.getenv("WHOOP_CLIENT_SECRET", "").strip(),
            redirect_uri=os.getenv("WHOOP_REDIRECT_URI", "").strip(),
            access_token=os.getenv("WHOOP_ACCESS_TOKEN", "").strip(),
            refresh_token=os.getenv("WHOOP_REFRESH_TOKEN", "").strip(),
            api_base=os.getenv("WHOOP_API_BASE", DEFAULT_WHOOP_API_BASE).strip() or DEFAULT_WHOOP_API_BASE,
            token_url=os.getenv("WHOOP_TOKEN_URL", DEFAULT_WHOOP_TOKEN_URL).strip() or DEFAULT_WHOOP_TOKEN_URL,
            token_store_path=token_store_path,
            access_token_expires_at=_parse_optional_float(os.getenv("WHOOP_ACCESS_TOKEN_EXPIRES_AT")),
            token_scope=os.getenv("WHOOP_TOKEN_SCOPE", "").strip(),
            token_type=os.getenv("WHOOP_TOKEN_TYPE", "bearer").strip() or "bearer",
        )
