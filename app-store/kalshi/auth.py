"""Kalshi API-key authentication provider."""

from __future__ import annotations

import base64
import time
from typing import Any

from truffile.app_runtime import ApiKeyProvider


class KalshiAuthProvider(ApiKeyProvider):
    def __init__(self, api_key: str, private_key_pem: str) -> None:
        if not api_key:
            raise ValueError("Missing Kalshi API key")
        if not private_key_pem:
            raise ValueError("Missing Kalshi private key")

        from cryptography.hazmat.primitives import serialization

        self._api_key = api_key
        self._private_key: Any = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=None,
        )

    def is_authenticated(self) -> bool:
        return bool(self._api_key and self._private_key is not None)

    def verify(self) -> tuple[bool, str]:
        if not self._api_key:
            return False, "Missing Kalshi API key"
        if self._private_key is None:
            return False, "Missing or invalid Kalshi private key"
        return True, "Kalshi credentials loaded"

    def get_auth_headers(self, method: str, path: str) -> dict[str, str]:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp}{method.upper()}{path}".encode("utf-8")
        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=hashes.SHA256().digest_size,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self._api_key,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }
