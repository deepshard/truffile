from __future__ import annotations

import unittest
from unittest.mock import patch

from truffile.app_runtime.testing import AppHarness

from client import AudioResult
from elevenlabs_foreground import ElevenLabsForegroundApp


class _FakeClient:
    def check_subscription(self):
        return {"tier": "free", "character_count": 10}

    def list_models(self):
        return [{"model_id": "eleven_multilingual_v2", "name": "Multilingual"}]

    def list_voices(self):
        return [{"voice_id": "voice-1", "name": "Rachel", "category": "premade"}]

    def search_voices(self, query="", limit=10):
        return self.list_voices()[:limit]

    def get_voice(self, voice_id):
        return {"voice_id": voice_id, "name": "Rachel"}

    def text_to_speech(self, **kwargs):
        return AudioResult(audio=b"fake-mp3", mime_type="audio/mpeg", extension="mp3", output_format=kwargs["output_format"])

    def text_to_sound_effect(self, **kwargs):
        return AudioResult(audio=b"fake-sfx", mime_type="audio/mpeg", extension="mp3", output_format=kwargs["output_format"])

    def create_composition_plan(self, **kwargs):
        return {"sections": [{"section_name": "Intro", "duration_ms": kwargs.get("music_length_ms") or 10000}]}

    def compose_music(self, **kwargs):
        return AudioResult(audio=b"fake-music", mime_type="audio/mpeg", extension="mp3", output_format=kwargs["output_format"])


class _FakeAudioBridge:
    configured = True

    def __init__(self):
        self.sent = []

    def send_audio(self, **kwargs):
        self.sent.append(kwargs)
        return {"filename": kwargs["filename"], "bytes": len(kwargs["audio_bytes"]), "played": kwargs["play"]}

    def list_files(self):
        return {"files": [{"filename": "tts_hi.mp3", "bytes": 8}]}

    def play_cached(self, filename):
        return {"filename": filename, "started": True}

    def stop_playback(self):
        return {"stopped": True, "pid": 123}


class TestElevenLabsAppShells(unittest.IsolatedAsyncioTestCase):
    async def test_foreground_generates_speech_and_sends_to_audio_bridge(self) -> None:
        bridge = _FakeAudioBridge()
        app = ElevenLabsForegroundApp(client=_FakeClient(), audio_bridge=bridge)
        harness = AppHarness(fg_app=app)

        result = await harness.run_fg(
            calls=[
                (
                    "text_to_speech",
                    {
                        "text": "hello from truffle",
                        "play_on_local_client": True,
                    },
                )
            ]
        )

        self.assertTrue(result.success)
        tool_result = result.tool_calls[0]["result"]
        self.assertEqual(tool_result["status"], "success")
        self.assertEqual(tool_result["bytes"], 8)
        self.assertEqual(tool_result["local_audio_bridge"]["played"], True)
        self.assertEqual(len(bridge.sent), 1)

    async def test_music_plan_and_music_generation(self) -> None:
        app = ElevenLabsForegroundApp(client=_FakeClient(), audio_bridge=_FakeAudioBridge())
        harness = AppHarness(fg_app=app)

        result = await harness.run_fg(
            calls=[
                ("create_composition_plan", {"prompt": "short synth intro", "music_length_ms": 12000}),
                ("compose_music", {"prompt": "short synth intro", "music_length_ms": 12000, "play_on_local_client": False}),
            ]
        )

        self.assertTrue(result.success)
        self.assertEqual(result.tool_calls[0]["result"]["status"], "success")
        self.assertEqual(result.tool_calls[1]["result"]["status"], "success")

    async def test_local_audio_tools_use_bridge(self) -> None:
        app = ElevenLabsForegroundApp(client=_FakeClient(), audio_bridge=_FakeAudioBridge())
        harness = AppHarness(fg_app=app)

        result = await harness.run_fg(
            calls=[
                ("list_local_audio", {}),
                ("play_local_audio", {"filename": "tts_hi.mp3"}),
                ("stop_local_audio", {}),
            ]
        )

        self.assertTrue(result.success)
        self.assertEqual(result.tool_calls[0]["result"]["files"][0]["filename"], "tts_hi.mp3")
        self.assertTrue(result.tool_calls[1]["result"]["playback"]["started"])
        self.assertTrue(result.tool_calls[2]["result"]["playback"]["stopped"])

    async def test_api_key_status_reports_environment_source(self) -> None:
        app = ElevenLabsForegroundApp(client=_FakeClient(), audio_bridge=_FakeAudioBridge())
        harness = AppHarness(fg_app=app)

        result = await harness.run_fg(calls=[("api_key_status", {})])

        self.assertTrue(result.success)
        self.assertEqual(result.tool_calls[0]["result"]["status"], "success")
        self.assertIn(result.tool_calls[0]["result"]["key_source"], {"missing", "environment", "file", "app_var"})

    async def test_reconfigure_api_key_validates_and_resets_client(self) -> None:
        app = ElevenLabsForegroundApp(client=_FakeClient(), audio_bridge=_FakeAudioBridge())
        harness = AppHarness(fg_app=app)

        with patch("elevenlabs_foreground.ElevenLabsClient", return_value=_FakeClient()), patch("elevenlabs_foreground.save_api_key") as save_api_key:
            result = await harness.run_fg(calls=[("reconfigure_api_key", {"api_key": "sk_test_new"})])

        self.assertTrue(result.success)
        self.assertEqual(result.tool_calls[0]["result"]["status"], "success")
        save_api_key.assert_called_once_with("sk_test_new")
