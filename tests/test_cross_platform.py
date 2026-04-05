import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from truffile.storage import StorageService, StoredState


class TestStoragePaths(unittest.TestCase):
    def test_storage_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "a" / "b" / "c"
            s = StorageService()
            s.storage_dir = nested
            s.state_file = nested / "state.json"
            s.state = StoredState()
            s.set_token("dev-1", "tok")
            self.assertTrue(s.state_file.exists())

    def test_storage_handles_unicode_device_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = StorageService()
            s.storage_dir = Path(tmp)
            s.state_file = Path(tmp) / "state.json"
            s.state = StoredState()
            s.set_token("truffle-café-☕", "tok")
            self.assertEqual(s.get_token("truffle-café-☕"), "tok")


class TestTerminalDetection(unittest.TestCase):
    def test_mushroom_disabled_when_not_tty(self):
        from truffile.cli.ui import MushroomPulse
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            pulse = MushroomPulse("test")
            self.assertFalse(pulse.enabled)

    def test_mushroom_enabled_when_tty(self):
        from truffile.cli.ui import MushroomPulse
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            pulse = MushroomPulse("test")
            self.assertTrue(pulse.enabled)


class TestPathHandling(unittest.TestCase):
    def test_slug_no_path_separators(self):
        from truffile.cli.create import _safe_app_slug
        slug = _safe_app_slug("my/app\\name")
        self.assertNotIn("/", slug)
        self.assertNotIn("\\", slug)

    def test_validate_handles_spaces_in_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            spaced = Path(tmp) / "my app dir"
            spaced.mkdir()
            (spaced / "truffile.yaml").write_text("metadata:\n  name: test\n")
            from truffile.schema.app_config import validate_app_dir
            validate_app_dir(spaced)


class TestWindowsCompat(unittest.TestCase):
    def test_storage_works_regardless_of_os(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = StorageService()
            s.storage_dir = Path(tmp)
            s.state_file = Path(tmp) / "state.json"
            s.state = StoredState()
            s.set_token("dev-1", "tok")
            self.assertEqual(s.get_token("dev-1"), "tok")
