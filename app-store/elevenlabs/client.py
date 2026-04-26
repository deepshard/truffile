from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class ElevenLabsError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, response: Any | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response


@dataclass(frozen=True)
class AudioResult:
    audio: bytes
    mime_type: str
    extension: str
    output_format: str


class ElevenLabsClient:
    def __init__(self, *, api_key: str, base_url: str = "https://api.elevenlabs.io", timeout: float = 90.0) -> None:
        if not api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def check_subscription(self) -> dict[str, Any]:
        return self._request_json("GET", "/v1/user/subscription")

    def list_models(self) -> list[dict[str, Any]]:
        data = self._request_json("GET", "/v1/models")
        return data if isinstance(data, list) else data.get("models", [])

    def list_voices(self) -> list[dict[str, Any]]:
        data = self._request_json("GET", "/v1/voices")
        voices = data.get("voices", []) if isinstance(data, dict) else []
        return voices if isinstance(voices, list) else []

    def search_voices(self, query: str = "", limit: int = 10) -> list[dict[str, Any]]:
        needle = query.strip().lower()
        voices = self.list_voices()
        if needle:
            voices = [
                voice
                for voice in voices
                if needle in str(voice.get("name", "")).lower()
                or needle in json.dumps(voice.get("labels", {}), sort_keys=True).lower()
                or needle in str(voice.get("category", "")).lower()
                or needle in str(voice.get("description", "")).lower()
            ]
        return voices[: max(1, min(limit, 50))]

    def get_voice(self, voice_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/v1/voices/{urllib.parse.quote(voice_id)}")

    def text_to_speech(
        self,
        *,
        text: str,
        voice_id: str,
        model_id: str,
        output_format: str,
        stability: float,
        similarity_boost: float,
        style: float,
        use_speaker_boost: bool,
        speed: float,
    ) -> AudioResult:
        if not text.strip():
            raise ElevenLabsError("Text is required")
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": style,
                "use_speaker_boost": use_speaker_boost,
                "speed": speed,
            },
        }
        audio = self._request_bytes(
            "POST",
            f"/v1/text-to-speech/{urllib.parse.quote(voice_id)}",
            params={"output_format": output_format},
            payload=payload,
        )
        return AudioResult(audio=audio, mime_type=_mime_for_output_format(output_format), extension=_extension_for_output_format(output_format), output_format=output_format)

    def text_to_sound_effect(
        self,
        *,
        text: str,
        duration_seconds: float,
        output_format: str,
        loop: bool,
    ) -> AudioResult:
        if not text.strip():
            raise ElevenLabsError("Sound effect description is required")
        if duration_seconds < 0.5 or duration_seconds > 5:
            raise ElevenLabsError("duration_seconds must be between 0.5 and 5")
        payload = {
            "text": text,
            "duration_seconds": duration_seconds,
            "loop": loop,
        }
        audio = self._request_bytes(
            "POST",
            "/v1/sound-generation",
            params={"output_format": output_format},
            payload=payload,
        )
        return AudioResult(audio=audio, mime_type=_mime_for_output_format(output_format), extension=_extension_for_output_format(output_format), output_format=output_format)

    def create_composition_plan(
        self,
        *,
        prompt: str,
        music_length_ms: int | None = None,
        source_composition_plan: dict[str, Any] | None = None,
        model_id: str = "music_v1",
    ) -> dict[str, Any]:
        if not prompt.strip():
            raise ElevenLabsError("Prompt is required")
        payload: dict[str, Any] = {"prompt": prompt}
        if music_length_ms is not None:
            if music_length_ms < 3000 or music_length_ms > 600000:
                raise ElevenLabsError("music_length_ms must be between 3000 and 600000")
            payload["music_length_ms"] = music_length_ms
        if source_composition_plan:
            payload["source_composition_plan"] = source_composition_plan
        if model_id:
            payload["model_id"] = model_id
        return self._request_json("POST", "/v1/music/plan", payload=payload)

    def compose_music(
        self,
        *,
        prompt: str | None = None,
        composition_plan: dict[str, Any] | None = None,
        music_length_ms: int | None = None,
        output_format: str = "mp3_44100_128",
        model_id: str = "music_v1",
        force_instrumental: bool = False,
    ) -> AudioResult:
        if not prompt and not composition_plan:
            raise ElevenLabsError("Provide prompt or composition_plan")
        if prompt and composition_plan:
            raise ElevenLabsError("Provide only one of prompt or composition_plan")
        if composition_plan and music_length_ms is not None:
            raise ElevenLabsError("music_length_ms cannot be used with composition_plan")
        payload: dict[str, Any] = {}
        if prompt:
            payload["prompt"] = prompt
        if composition_plan:
            payload["composition_plan"] = composition_plan
        if music_length_ms is not None:
            payload["music_length_ms"] = music_length_ms
        if model_id:
            payload["model_id"] = model_id
        if prompt:
            payload["force_instrumental"] = force_instrumental
        audio = self._request_bytes(
            "POST",
            "/v1/music",
            params={"output_format": output_format},
            payload=payload,
            timeout=180.0,
        )
        return AudioResult(audio=audio, mime_type=_mime_for_output_format(output_format), extension=_extension_for_output_format(output_format), output_format=output_format)

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
        raw = self._request(method, path, payload=payload, params=params)
        text = raw.decode("utf-8", errors="replace")
        try:
            return json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            raise ElevenLabsError(f"Expected JSON response from ElevenLabs, got: {text[:200]}") from exc

    def _request_bytes(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> bytes:
        return self._request(method, path, payload=payload, params=params, timeout=timeout)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> bytes:
        url = self.base_url + path
        clean_params = {key: value for key, value in (params or {}).items() if value is not None}
        if clean_params:
            url += "?" + urllib.parse.urlencode(clean_params)
        body = None
        headers = {
            "xi-api-key": self.api_key,
            "Accept": "*/*",
        }
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=timeout or self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            parsed: Any = None
            try:
                parsed = json.loads(body_text)
            except json.JSONDecodeError:
                parsed = body_text
            raise ElevenLabsError(f"ElevenLabs HTTP {exc.code}: {body_text[:500]}", status_code=exc.code, response=parsed) from exc
        except Exception as exc:
            raise ElevenLabsError(f"ElevenLabs request failed: {exc}") from exc


def _mime_for_output_format(output_format: str) -> str:
    if output_format.startswith("pcm_"):
        return "audio/wav"
    if output_format.startswith("opus_"):
        return "audio/opus"
    if output_format.startswith("ulaw_") or output_format.startswith("alaw_"):
        return "audio/basic"
    return "audio/mpeg"


def _extension_for_output_format(output_format: str) -> str:
    if output_format.startswith("pcm_"):
        return "wav"
    if output_format.startswith("opus_"):
        return "opus"
    if output_format.startswith("ulaw_"):
        return "ulaw"
    if output_format.startswith("alaw_"):
        return "alaw"
    return "mp3"
