import tempfile
import unittest
from pathlib import Path

from truffile.cli.obsidian_bridge import (
    VaultBridge,
    describe_vault_permission_error,
    normalize_relative_path,
    normalize_vault_path,
)


class TestObsidianBridgePaths(unittest.TestCase):
    def test_normalize_vault_path_requires_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = normalize_vault_path(tmp)
            self.assertEqual(path, Path(tmp).resolve())

    def test_normalize_relative_path_rejects_parent_escape(self):
        with self.assertRaises(ValueError):
            normalize_relative_path("../secret.md")

    def test_normalize_relative_path_allows_root(self):
        self.assertEqual(normalize_relative_path("/", allow_root=True), Path("."))

    def test_permission_message_mentions_macos_guidance(self):
        message = describe_vault_permission_error(Path("/Users/test/Documents/vault"))
        self.assertIn("vault path", message)


class TestVaultBridge(unittest.TestCase):
    def test_read_write_search_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bridge = VaultBridge(root)

            write_result = bridge.write_note("notes/today.md", "alpha beta gamma")
            self.assertEqual(write_result["path"], "notes/today.md")

            note = bridge.read_note("notes/today.md")
            self.assertEqual(note["content"], "alpha beta gamma")

            search_results = bridge.search("beta", context_length=5)
            self.assertEqual(len(search_results), 1)
            self.assertEqual(search_results[0]["filename"], "notes/today.md")

    def test_list_files_skips_hidden_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".obsidian").mkdir()
            (root / ".obsidian" / "plugins.md").write_text("ignored", encoding="utf-8")
            (root / "visible").mkdir()
            (root / "visible" / "note.md").write_text("hello", encoding="utf-8")

            bridge = VaultBridge(root)
            entries = bridge.list_files("/")
            self.assertEqual(entries, ["visible/"])

    def test_write_rejects_symlink_outside_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "vault"
            root.mkdir()
            outside = base / "outside.md"
            outside.write_text("outside", encoding="utf-8")
            link = root / "linked.md"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")

            bridge = VaultBridge(root)
            with self.assertRaises(ValueError):
                bridge.write_note("linked.md", "overwrite")

            self.assertEqual(outside.read_text(encoding="utf-8"), "outside")

    def test_search_skips_symlink_outside_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "vault"
            root.mkdir()
            outside = base / "outside.md"
            outside.write_text("outside secret", encoding="utf-8")
            link = root / "linked.md"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")

            bridge = VaultBridge(root)
            self.assertEqual(bridge.search("outside secret"), [])
