from __future__ import annotations

import argparse
import asyncio
import base64
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from truffile.app_runtime import ForegroundApp, ToolSpec, err, ok

from audio_bridge_client import AudioBridgeClient, AudioBridgeError
from client import AudioResult, ElevenLabsClient, ElevenLabsError
from config import (
    DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_VOICE_ID,
    ELEVENLABS_API_BASE,
    OUTPUT_DIR,
    TRUFFILE_AUDIO_BRIDGE_BASE_URL,
    TRUFFILE_AUDIO_BRIDGE_TOKEN,
)
from credential_store import api_key_source, load_api_key, save_api_key


SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _clean_filename(prefix: str, seed: str, extension: str) -> str:
    snippet = SAFE_NAME_RE.sub("_", seed.strip()[:36]).strip("._") or "audio"
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{snippet}_{stamp}.{extension}"


def _write_output(filename: str, audio: bytes) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    path.write_bytes(audio)
    return path


def _summarize_voice(voice: dict[str, Any]) -> dict[str, Any]:
    return {
        "voice_id": voice.get("voice_id"),
        "name": voice.get("name"),
        "category": voice.get("category"),
        "labels": voice.get("labels") or {},
        "description": voice.get("description"),
        "preview_url": voice.get("preview_url"),
    }


class ElevenLabsForegroundApp(ForegroundApp):
    def __init__(
        self,
        *,
        client: ElevenLabsClient | None = None,
        audio_bridge: AudioBridgeClient | None = None,
    ) -> None:
        super().__init__("elevenlabs", logger_name="elevenlabs.foreground")
        self._client = client
        self._audio_bridge = audio_bridge
        self._register_tools()

    def _get_client(self) -> ElevenLabsClient:
        if self._client is None:
            self._client = ElevenLabsClient(api_key=load_api_key(), base_url=ELEVENLABS_API_BASE)
        return self._client

    def _get_audio_bridge(self) -> AudioBridgeClient:
        if self._audio_bridge is None:
            self._audio_bridge = AudioBridgeClient(
                base_url=TRUFFILE_AUDIO_BRIDGE_BASE_URL,
                token=TRUFFILE_AUDIO_BRIDGE_TOKEN,
            )
        return self._audio_bridge

    def _store_and_maybe_play(
        self,
        *,
        result: AudioResult,
        filename: str,
        play_on_local_client: bool,
        include_audio_base64: bool,
    ) -> dict[str, Any]:
        output_path = _write_output(filename, result.audio)
        payload: dict[str, Any] = {
            "filename": filename,
            "container_path": str(output_path),
            "mime_type": result.mime_type,
            "output_format": result.output_format,
            "bytes": len(result.audio),
            "local_audio_bridge": None,
        }

        bridge = self._get_audio_bridge()
        if play_on_local_client or bridge.configured:
            if not bridge.configured:
                payload["local_audio_bridge"] = {
                    "status": "not_configured",
                    "message": "Deploy with `truffile audio deploy --path apps/elevenlabs` to enable local playback.",
                }
            else:
                try:
                    payload["local_audio_bridge"] = bridge.send_audio(
                        filename=filename,
                        audio_bytes=result.audio,
                        mime_type=result.mime_type,
                        play=play_on_local_client,
                    )
                except AudioBridgeError as exc:
                    payload["local_audio_bridge"] = {"status": "error", "message": str(exc)}

        if include_audio_base64:
            payload["audio_base64"] = base64.b64encode(result.audio).decode("ascii")
        return payload

    def _register_tools(self) -> None:
        @self.tool(
            ToolSpec(
                name="reconfigure_api_key",
                description=(
                    "Rotate the ElevenLabs API key used by this installed app. "
                    "The key is validated before being stored, and future tool calls use the new key."
                ),
                icon="key",
            )
        )
        async def reconfigure_api_key_tool(api_key: str) -> dict[str, Any]:
            cleaned = api_key.strip()
            if not cleaned:
                return err("API key is required")
            try:
                test_client = ElevenLabsClient(api_key=cleaned, base_url=ELEVENLABS_API_BASE)
                subscription = test_client.check_subscription()
                save_api_key(cleaned)
                self._client = ElevenLabsClient(api_key=cleaned, base_url=ELEVENLABS_API_BASE)
                return ok(
                    "ElevenLabs API key updated",
                    key_source=api_key_source(),
                    subscription=subscription,
                )
            except ElevenLabsError as exc:
                return err(str(exc), status_code=exc.status_code, response=exc.response)
            except Exception as exc:
                return err(f"Could not store ElevenLabs API key: {exc}")

        @self.tool(
            ToolSpec(
                name="api_key_status",
                description="Show where the ElevenLabs API key is currently loaded from without revealing the key.",
                icon="shield-check",
                readonly=True,
            )
        )
        async def api_key_status_tool() -> dict[str, Any]:
            source = api_key_source()
            return ok("API key status fetched", key_source=source, configured=source != "missing")

        @self.tool(
            ToolSpec(
                name="check_subscription",
                description="Check the configured ElevenLabs account subscription and quota state.",
                icon="identification-card",
                readonly=True,
            )
        )
        async def check_subscription_tool() -> dict[str, Any]:
            try:
                return ok("Subscription fetched", subscription=self._get_client().check_subscription())
            except ElevenLabsError as exc:
                return err(str(exc), status_code=exc.status_code, response=exc.response)

        @self.tool(
            ToolSpec(
                name="list_models",
                description="List ElevenLabs models available to the configured account.",
                icon="list",
                readonly=True,
            )
        )
        async def list_models_tool() -> dict[str, Any]:
            try:
                models = self._get_client().list_models()
                return ok("Models fetched", models=models, count=len(models))
            except ElevenLabsError as exc:
                return err(str(exc), status_code=exc.status_code, response=exc.response)

        @self.tool(
            ToolSpec(
                name="search_voices",
                description="Search voices in the user's ElevenLabs voice library by name, label, category, or description.",
                icon="microphone-stage",
                readonly=True,
            )
        )
        async def search_voices_tool(query: str = "", limit: int = 10) -> dict[str, Any]:
            try:
                voices = [_summarize_voice(voice) for voice in self._get_client().search_voices(query=query, limit=limit)]
                return ok("Voices fetched", voices=voices, count=len(voices))
            except ElevenLabsError as exc:
                return err(str(exc), status_code=exc.status_code, response=exc.response)

        @self.tool(
            ToolSpec(
                name="get_voice",
                description="Fetch detailed metadata for one ElevenLabs voice by voice_id.",
                icon="user-sound",
                readonly=True,
            )
        )
        async def get_voice_tool(voice_id: str) -> dict[str, Any]:
            try:
                return ok("Voice fetched", voice=self._get_client().get_voice(voice_id))
            except ElevenLabsError as exc:
                return err(str(exc), status_code=exc.status_code, response=exc.response)

        @self.tool(
            ToolSpec(
                name="text_to_speech",
                description=(
                    "Generate speech audio from text. This spends ElevenLabs credits. "
                    "By default the result is sent to the local Truffile audio bridge for playback when configured."
                ),
                icon="speaker-high",
            )
        )
        async def text_to_speech_tool(
            text: str,
            voice_id: str = DEFAULT_VOICE_ID,
            model_id: str = DEFAULT_MODEL_ID,
            output_format: str = DEFAULT_OUTPUT_FORMAT,
            stability: float = 0.5,
            similarity_boost: float = 0.75,
            style: float = 0.0,
            use_speaker_boost: bool = True,
            speed: float = 1.0,
            play_on_local_client: bool = True,
            include_audio_base64: bool = False,
        ) -> dict[str, Any]:
            try:
                audio = self._get_client().text_to_speech(
                    text=text,
                    voice_id=voice_id,
                    model_id=model_id,
                    output_format=output_format,
                    stability=stability,
                    similarity_boost=similarity_boost,
                    style=style,
                    use_speaker_boost=use_speaker_boost,
                    speed=speed,
                )
                stored = self._store_and_maybe_play(
                    result=audio,
                    filename=_clean_filename("tts", text, audio.extension),
                    play_on_local_client=play_on_local_client,
                    include_audio_base64=include_audio_base64,
                )
                return ok("Speech generated", **stored)
            except ElevenLabsError as exc:
                return err(str(exc), status_code=exc.status_code, response=exc.response)

        @self.tool(
            ToolSpec(
                name="text_to_sound_effect",
                description="Generate a short sound effect from a text description. This spends ElevenLabs credits.",
                icon="waveform",
            )
        )
        async def text_to_sound_effect_tool(
            text: str,
            duration_seconds: float = 2.0,
            output_format: str = DEFAULT_OUTPUT_FORMAT,
            loop: bool = False,
            play_on_local_client: bool = True,
            include_audio_base64: bool = False,
        ) -> dict[str, Any]:
            try:
                audio = self._get_client().text_to_sound_effect(
                    text=text,
                    duration_seconds=duration_seconds,
                    output_format=output_format,
                    loop=loop,
                )
                stored = self._store_and_maybe_play(
                    result=audio,
                    filename=_clean_filename("sfx", text, audio.extension),
                    play_on_local_client=play_on_local_client,
                    include_audio_base64=include_audio_base64,
                )
                return ok("Sound effect generated", **stored)
            except ElevenLabsError as exc:
                return err(str(exc), status_code=exc.status_code, response=exc.response)

        @self.tool(
            ToolSpec(
                name="create_composition_plan",
                description="Create a structured Eleven Music composition plan from a prompt. This is rate-limited but does not spend generation credits.",
                icon="music-notes",
                readonly=True,
            )
        )
        async def create_composition_plan_tool(
            prompt: str,
            music_length_ms: int | None = None,
            source_composition_plan: dict[str, Any] | None = None,
            model_id: str = "music_v1",
        ) -> dict[str, Any]:
            try:
                plan = self._get_client().create_composition_plan(
                    prompt=prompt,
                    music_length_ms=music_length_ms,
                    source_composition_plan=source_composition_plan,
                    model_id=model_id,
                )
                return ok("Composition plan created", composition_plan=plan)
            except ElevenLabsError as exc:
                return err(str(exc), status_code=exc.status_code, response=exc.response)

        @self.tool(
            ToolSpec(
                name="compose_music",
                description=(
                    "Generate a music track from a prompt or composition plan. This spends ElevenLabs Music credits "
                    "and may require a paid ElevenLabs plan."
                ),
                icon="music-note",
            )
        )
        async def compose_music_tool(
            prompt: str | None = None,
            composition_plan: dict[str, Any] | None = None,
            music_length_ms: int | None = None,
            output_format: str = DEFAULT_OUTPUT_FORMAT,
            model_id: str = "music_v1",
            force_instrumental: bool = False,
            play_on_local_client: bool = True,
            include_audio_base64: bool = False,
        ) -> dict[str, Any]:
            try:
                audio = self._get_client().compose_music(
                    prompt=prompt,
                    composition_plan=composition_plan,
                    music_length_ms=music_length_ms,
                    output_format=output_format,
                    model_id=model_id,
                    force_instrumental=force_instrumental,
                )
                seed = prompt or "composition_plan"
                stored = self._store_and_maybe_play(
                    result=audio,
                    filename=_clean_filename("music", seed, audio.extension),
                    play_on_local_client=play_on_local_client,
                    include_audio_base64=include_audio_base64,
                )
                return ok("Music generated", **stored)
            except ElevenLabsError as exc:
                return err(str(exc), status_code=exc.status_code, response=exc.response)

        @self.tool(
            ToolSpec(
                name="list_local_audio",
                description="List audio files cached by the local Truffile audio bridge.",
                icon="folder-open",
                readonly=True,
            )
        )
        async def list_local_audio_tool() -> dict[str, Any]:
            bridge = self._get_audio_bridge()
            if not bridge.configured:
                return err("Local audio bridge is not configured")
            try:
                return ok("Local audio files fetched", **bridge.list_files())
            except AudioBridgeError as exc:
                return err(str(exc))

        @self.tool(
            ToolSpec(
                name="play_local_audio",
                description="Play an audio file already cached by the local Truffile audio bridge.",
                icon="play",
            )
        )
        async def play_local_audio_tool(filename: str) -> dict[str, Any]:
            bridge = self._get_audio_bridge()
            if not bridge.configured:
                return err("Local audio bridge is not configured")
            try:
                return ok("Playback requested", playback=bridge.play_cached(filename))
            except AudioBridgeError as exc:
                return err(str(exc))

        @self.tool(
            ToolSpec(
                name="stop_local_audio",
                description="Stop the currently tracked local audio playback process started by the Truffile audio bridge.",
                icon="stop",
            )
        )
        async def stop_local_audio_tool() -> dict[str, Any]:
            bridge = self._get_audio_bridge()
            if not bridge.configured:
                return err("Local audio bridge is not configured")
            try:
                return ok("Stop requested", playback=bridge.stop_playback())
            except AudioBridgeError as exc:
                return err(str(exc))


app = ElevenLabsForegroundApp()


async def _verify() -> int:
    app_for_verify = ElevenLabsForegroundApp()
    result = await app_for_verify.invoke_tool("check_subscription")
    if result.get("status") == "success":
        print("ElevenLabs API key verified")
        return 0
    print(result.get("message", "ElevenLabs verification failed"))
    return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        raise SystemExit(asyncio.run(_verify()))
    app.run()
