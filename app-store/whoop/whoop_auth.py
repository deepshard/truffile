"""WHOOP OAuth token helpers for manual-token Truffle installs."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Callable

from truffile.app_runtime import AppAuthError, OAuth

from config import WhoopConfig


class WhoopOAuth(OAuth):
    APP_VAR_KEY = "whoop_oauth"

    def __init__(
        self,
        config: WhoopConfig | None = None,
        *,
        read_only: bool = False,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._config = config or WhoopConfig.from_env()
        self._time_fn = time_fn or time.time
        super().__init__(self._config.token_store_path, read_only=read_only)

    @staticmethod
    def token_from_payload(payload: dict[str, Any]) -> str:
        return str(payload.get("access_token", "") or "").strip()

    def config_errors(self) -> list[str]:
        errors: list[str] = []
        if not self._config.client_id:
            errors.append("WHOOP_CLIENT_ID is missing")
        if not self._config.client_secret:
            errors.append("WHOOP_CLIENT_SECRET is missing")
        if not self._config.redirect_uri:
            errors.append("WHOOP_REDIRECT_URI is missing")
        payload = self.get_oauth_payload() or {}
        if not self.token_from_payload(payload):
            errors.append("WHOOP access token is missing")
        if not str(payload.get("refresh_token", "") or "").strip():
            errors.append("WHOOP refresh token is missing")
        return errors

    def verify(self) -> tuple[bool, str]:
        errors = self.config_errors()
        if errors:
            return False, "; ".join(errors)
        return True, "WHOOP OAuth credentials loaded"

    def get_client_id(self) -> str:
        return self._config.client_id

    def get_client_secret(self) -> str:
        return self._config.client_secret

    def get_redirect_uri(self) -> str:
        return self._config.redirect_uri

    def get_refresh_token(self) -> str:
        payload = self.get_oauth_payload() or {}
        token = str(payload.get("refresh_token", "") or "").strip()
        if not token:
            raise AppAuthError("WHOOP refresh token missing")
        return token

    def can_refresh(self) -> bool:
        return bool(
            self._config.client_id
            and self._config.client_secret
            and str((self.get_oauth_payload() or {}).get("refresh_token", "") or "").strip()
        )

    def get_auth_headers(self) -> dict[str, str]:
        token = self.get_access_token()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def token_expires_soon(self, *, leeway_seconds: float = 120.0) -> bool:
        expires_at_value = self._token_expires_at_value()
        if expires_at_value is None:
            return False
        return self._time_fn() + leeway_seconds >= expires_at_value

    def remember_token_response(
        self,
        payload: dict[str, Any],
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        current = self.get_oauth_payload() or {}
        merged = dict(current)
        merged.update({key: value for key, value in payload.items() if value is not None})
        if "expires_in" in payload:
            try:
                merged["expires_at"] = float(now if now is not None else self._time_fn()) + float(payload["expires_in"])
            except (TypeError, ValueError):
                merged.pop("expires_at", None)
        merged["token_type"] = str(merged.get("token_type", "bearer") or "bearer").strip() or "bearer"
        self.save_oauth_payload(merged)
        return merged

    def status(self) -> dict[str, Any]:
        payload = self.get_oauth_payload() or {}
        expires_at_value = self._token_expires_at_value(payload)
        seconds_remaining = None
        expires_at_utc = None
        token_expired = None
        token_expires_soon = None
        if expires_at_value is not None:
            now = self._time_fn()
            seconds_remaining = max(0, int(expires_at_value - now))
            expires_at_utc = datetime.fromtimestamp(expires_at_value, tz=timezone.utc).isoformat()
            token_expired = now >= expires_at_value
            token_expires_soon = now + 120.0 >= expires_at_value
        return {
            "client_id_configured": bool(self._config.client_id),
            "client_secret_configured": bool(self._config.client_secret),
            "redirect_uri_configured": bool(self._config.redirect_uri),
            "access_token_present": bool(self.token_from_payload(payload)),
            "refresh_token_present": bool(str(payload.get("refresh_token", "") or "").strip()),
            "token_expires_at": payload.get("expires_at"),
            "token_expires_at_unix": expires_at_value,
            "token_expires_at_utc": expires_at_utc,
            "token_seconds_remaining": seconds_remaining,
            "token_expired": token_expired,
            "token_expires_soon": token_expires_soon,
            "scope": str(payload.get("scope", "") or "").strip(),
            "token_type": str(payload.get("token_type", "bearer") or "bearer").strip() or "bearer",
            "token_store_path": str(self.token_file),
        }

    def get_oauth_payload(self) -> dict[str, Any] | None:
        payload = super().get_oauth_payload()
        if payload:
            return payload
        env_payload = self._payload_from_env()
        if env_payload and self.token_from_payload(env_payload) and not self._read_only:
            self.save_oauth_payload(env_payload)
        return env_payload

    def _payload_from_env(self) -> dict[str, Any] | None:
        payload: dict[str, Any] = {}
        if self._config.access_token:
            payload["access_token"] = self._config.access_token
        if self._config.refresh_token:
            payload["refresh_token"] = self._config.refresh_token
        if self._config.access_token_expires_at is not None:
            payload["expires_at"] = self._config.access_token_expires_at
        if self._config.token_scope:
            payload["scope"] = self._config.token_scope
        if self._config.token_type:
            payload["token_type"] = self._config.token_type
        return payload or None

    def _token_expires_at_value(self, payload: dict[str, Any] | None = None) -> float | None:
        payload = payload if payload is not None else self.get_oauth_payload() or {}
        try:
            return float(payload.get("expires_at"))
        except (TypeError, ValueError):
            return None
