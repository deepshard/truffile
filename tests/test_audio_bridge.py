from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from truffile.cli.audio_bridge import AudioBridge


class TestAudioBridge(unittest.TestCase):
    def test_save_list_and_read_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bridge = AudioBridge(Path(tmp))
            result = bridge.save_audio(
                filename="../hello world.mp3",
                data_base64=base64.b64encode(b"audio-bytes").decode("ascii"),
                mime_type="audio/mpeg",
                play=False,
            )

            self.assertEqual(result["filename"], "hello_world.mp3")
            self.assertEqual(result["bytes"], len(b"audio-bytes"))
            files = bridge.list_files()
            self.assertEqual(files[0]["filename"], "hello_world.mp3")
            path, data = bridge.read_audio("hello_world.mp3")
            self.assertEqual(path.name, "hello_world.mp3")
            self.assertEqual(data, b"audio-bytes")

    def test_play_request_uses_player(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bridge = AudioBridge(Path(tmp))
            bridge.save_audio(
                filename="clip.mp3",
                data_base64=base64.b64encode(b"audio-bytes").decode("ascii"),
                play=False,
            )
            with patch("truffile.cli.audio_bridge._candidate_player_commands", return_value=[["fake-player", "clip.mp3"]]), patch(
                "truffile.cli.audio_bridge.subprocess.Popen"
            ) as popen:
                result = bridge.play_cached("clip.mp3")

            self.assertTrue(result["started"])
            self.assertEqual(result["filename"], "clip.mp3")
            popen.assert_called_once()

    def test_stop_playback_terminates_tracked_player(self) -> None:
        class FakeProcess:
            pid = 123

            def __init__(self) -> None:
                self.terminated = False

            def poll(self):
                return None

            def terminate(self) -> None:
                self.terminated = True

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            bridge = AudioBridge(Path(tmp))
            bridge.save_audio(
                filename="clip.mp3",
                data_base64=base64.b64encode(b"audio-bytes").decode("ascii"),
                play=False,
            )
            fake = FakeProcess()
            with patch("truffile.cli.audio_bridge._candidate_player_commands", return_value=[["fake-player", "clip.mp3"]]), patch(
                "truffile.cli.audio_bridge.subprocess.Popen", return_value=fake
            ):
                bridge.play_cached("clip.mp3")
                result = bridge.stop_playback()

            self.assertTrue(result["stopped"])
            self.assertTrue(fake.terminated)
