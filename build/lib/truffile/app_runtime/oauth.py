# base class for OAuth auth with app var + file dual-write pattern.
# subclasses set APP_VAR_KEY and override token_from_payload().

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("app_runtime.oauth")


class OAuth:
    APP_VAR_KEY: str = "oauth_state"

    def __init__(self, token_file: Path, read_only: bool = False) -> None:
        self.token_file = token_file
        self._read_only = read_only

    @staticmethod
    def _runtime_app_vars_enabled() -> bool:
        return bool(
            str(os.getenv("APP_ID", "")).strip()
            and str(os.getenv("APP_SESSION_TOKEN", "")).strip()
        )

    def _load_serialized_from_app_var(self) -> str | None:
        if not self._runtime_app_vars_enabled():
            return None
        try:
            from app_runtime import AppRuntimeClient, init_channel

            with init_channel() as channel:
                client = AppRuntimeClient(channel)
                return client.get_app_var(self.APP_VAR_KEY)
        except Exception:
            LOGGER.debug("failed to load %s from app vars", self.APP_VAR_KEY, exc_info=True)
            return None

    def _save_serialized_to_app_var(self, serialized: str) -> None:
        if self._read_only or not self._runtime_app_vars_enabled():
            return
        try:
            from app_runtime import AppRuntimeClient, init_channel

            with init_channel() as channel:
                client = AppRuntimeClient(channel)
                client.set_app_var(self.APP_VAR_KEY, serialized)
        except Exception:
            LOGGER.debug("failed to save %s to app vars", self.APP_VAR_KEY, exc_info=True)

    def _delete_app_var(self) -> None:
        if not self._runtime_app_vars_enabled():
            return
        try:
            from app_runtime import AppRuntimeClient, init_channel

            with init_channel() as channel:
                client = AppRuntimeClient(channel)
                client.delete_app_var(self.APP_VAR_KEY)
        except Exception:
            LOGGER.debug("failed to delete %s from app vars", self.APP_VAR_KEY, exc_info=True)


    def _load_payload_from_file(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.token_file.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _save_payload_to_file(self, payload: dict[str, Any]) -> None:
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _serialize(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))



    @staticmethod
    def token_from_payload(payload: dict[str, Any]) -> str:
        """Extract the usable token string from a payload dict. Override per app."""
        return str(payload.get("access_token", "") or "").strip()



    def get_oauth_payload(self) -> dict[str, Any] | None:
        """Load token: app var first, file fallback, sync back if needed."""
        serialized = self._load_serialized_from_app_var()
        if serialized:
            try:
                payload = json.loads(serialized)
            except Exception:
                payload = None
            if isinstance(payload, dict) and self.token_from_payload(payload):
                if not self._read_only:
                    self._save_payload_to_file(payload)
                return payload

        payload = self._load_payload_from_file()
        if isinstance(payload, dict) and self.token_from_payload(payload):
            if not self._read_only:
                self._save_serialized_to_app_var(self._serialize(payload))
            return payload

        return None

    def save_oauth_payload(self, payload: dict[str, Any]) -> None:
        """save to file and app var."""
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict")
        self._save_payload_to_file(payload)
        self._save_serialized_to_app_var(self._serialize(payload))

    def get_access_token(self) -> str:
        payload = self.get_oauth_payload()
        if not isinstance(payload, dict):
            return ""
        return self.token_from_payload(payload)
