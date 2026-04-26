from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class AudioBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioBridgeClient:
    base_url: str
    token: str
    timeout: float = 20.0

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/health")

    def list_files(self) -> dict[str, Any]:
        return self._request_json("GET", "/files")

    def send_audio(
        self,
        *,
        filename: str,
        audio_bytes: bytes,
        mime_type: str,
        play: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "filename": filename,
            "mime_type": mime_type,
            "data_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "play": play,
        }
        return self._request_json("POST", "/audio", payload)

    def play_cached(self, filename: str) -> dict[str, Any]:
        return self._request_json("POST", "/play", {"filename": filename})

    def stop_playback(self) -> dict[str, Any]:
        return self._request_json("POST", "/stop", {})

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise AudioBridgeError("Local audio bridge is not configured")
        body = None
        headers = {"Authorization": f"Bearer {self.token}"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base_url.rstrip("/") + path,
            data=body,
            headers=headers,
            method=method,
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AudioBridgeError(f"Audio bridge HTTP {exc.code}: {detail}") from exc
        except Exception as exc:
            raise AudioBridgeError(f"Audio bridge request failed: {exc}") from exc
