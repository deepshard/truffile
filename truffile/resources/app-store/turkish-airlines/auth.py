from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any

from config import (
    TURKISH_AIRLINES_AUTH_TOKEN_ENDPOINT,
    TURKISH_AIRLINES_OAUTH_APP_VAR_KEY,
    TURKISH_AIRLINES_OAUTH_RESOURCE,
    resolve_token_file,
)
from remote_mcp_compat import load_remote_mcp

RemoteMcpOAuth = load_remote_mcp().RemoteMcpOAuth


REFRESH_SKEW_SECONDS = 300


class TurkishAirlinesAuth(RemoteMcpOAuth):
    def __init__(self, token_file: Path | None = None, read_only: bool = False) -> None:
        resolved = Path(token_file) if token_file is not None else resolve_token_file()
        env_access_token = str(os.getenv("TURKISH_AIRLINES_ACCESS_TOKEN", "") or "").strip()
        super().__init__(
            resolved,
            app_var_key=TURKISH_AIRLINES_OAUTH_APP_VAR_KEY,
            env_access_token=env_access_token,
            default_token_endpoint=TURKISH_AIRLINES_AUTH_TOKEN_ENDPOINT,
            default_resource=TURKISH_AIRLINES_OAUTH_RESOURCE,
            read_only=read_only,
        )

    def get_access_token(self) -> str:
        if self.env_access_token:
            return self.env_access_token
        return self.ensure_access_token_fresh()

    def ensure_access_token_fresh(self) -> str:
        payload = self.get_oauth_payload()
        if not isinstance(payload, dict):
            return ""
        if self._needs_refresh(payload):
            if self._read_only:
                return self.token_from_payload(payload)
            try:
                return self.refresh_access_token()
            except Exception:
                reloaded = self.get_oauth_payload()
                if isinstance(reloaded, dict) and not self._needs_refresh(reloaded):
                    return self.token_from_payload(reloaded)
                raise
        return self.token_from_payload(payload)

    def refresh_access_token(self) -> str:
        token = super().refresh_access_token()
        payload = self.get_oauth_payload()
        if isinstance(payload, dict):
            self._set_expiry_fields(payload)
            self.save_oauth_payload(payload)
        return token

    @staticmethod
    def _set_expiry_fields(payload: dict[str, Any]) -> None:
        expires_in = payload.get("expires_in")
        try:
            seconds = int(expires_in)
        except (TypeError, ValueError):
            return
        if seconds > 0:
            payload["expires_at"] = int(time.time()) + seconds

    @staticmethod
    def _needs_refresh(payload: dict[str, Any]) -> bool:
        expires_at = _expiry_epoch(payload)
        if expires_at is None:
            return False
        return expires_at - time.time() <= REFRESH_SKEW_SECONDS


def _expiry_epoch(payload: dict[str, Any]) -> float | None:
    for key in ("expires_at", "expiresAt", "expiry", "expires"):
        raw = payload.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            return float(raw)
        value = str(raw).strip()
        if not value:
            continue
        try:
            return float(value)
        except ValueError:
            pass
    return None