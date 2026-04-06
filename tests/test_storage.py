import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from truffile.storage import StorageService, StoredState


class TestStorageRoundTrip(unittest.TestCase):
    def _make_storage(self, tmp_dir: str) -> StorageService:
        storage = StorageService()
        storage.storage_dir = Path(tmp_dir)
        storage.state_file = Path(tmp_dir) / "state.json"
        storage.state = StoredState()
        return storage

    def test_set_and_get_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._make_storage(tmp)
            s.set_token("truffle-1234", "tok_abc")
            self.assertEqual(s.get_token("truffle-1234"), "tok_abc")

    def test_get_nonexistent_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._make_storage(tmp)
            self.assertIsNone(s.get_token("truffle-9999"))

    def test_list_devices(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._make_storage(tmp)
            s.set_token("truffle-1", "tok_1")
            s.set_token("truffle-2", "tok_2")
            devices = s.list_devices()
            self.assertEqual(len(devices), 2)

    def test_remove_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._make_storage(tmp)
            s.set_token("truffle-1", "tok_1")
            s.remove_device("truffle-1")
            self.assertIsNone(s.get_token("truffle-1"))

    def test_clear_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._make_storage(tmp)
            s.set_token("truffle-1", "tok_1")
            s.set_token("truffle-2", "tok_2")
            s.clear_all()
            self.assertEqual(len(s.list_devices()), 0)

    def test_set_last_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._make_storage(tmp)
            s.set_token("truffle-1", "tok_1")
            s.set_last_used("truffle-1")
            self.assertEqual(s.state.last_used_device, "truffle-1")

    def test_overwrite_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._make_storage(tmp)
            s.set_token("truffle-1", "tok_old")
            s.set_token("truffle-1", "tok_new")
            self.assertEqual(s.get_token("truffle-1"), "tok_new")

    def test_state_persists_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._make_storage(tmp)
            s.set_token("truffle-1", "tok_1")
            self.assertTrue(s.state_file.exists())

    def test_corrupt_state_file_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._make_storage(tmp)
            s.state_file.write_text("not json {{{")
            state = s._load_state()
            self.assertIsNotNone(state)


class TestStorageFilePermissions(unittest.TestCase):
    def test_token_file_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = StorageService()
            s.storage_dir = Path(tmp)
            s.state_file = Path(tmp) / "state.json"
            s.state = StoredState()
            s.set_token("truffle-1", "tok_secret")
            self.assertTrue(s.state_file.exists())
