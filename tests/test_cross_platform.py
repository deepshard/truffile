import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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
    def test_particle_orb_creates(self):
        from truffile.cli.ui import create_thinking_orb
        orb = create_thinking_orb()
        self.assertIsNotNone(orb)

    def test_particle_orb_state_changes(self):
        from truffile.cli.art import ParticleOrb
        orb = ParticleOrb(num_particles=3)
        orb.set_state(ParticleOrb.STATE_ACTIVE)
        orb.set_state(ParticleOrb.STATE_DONE)


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


def test_scan_json_in_container_never_prompts(monkeypatch, capsys):
    from truffile.cli import connect

    info = SimpleNamespace(
        device_name="truffle-container",
        ip_address="10.0.0.2",
        grpc_address="host:80",
        serial="",
        mac_address="",
        firmware_version="",
        timezone="",
        probe_failed=False,
    )
    monkeypatch.setattr(connect, "probe_in_container_device", lambda: info)
    storage = SimpleNamespace(get_token=lambda name: "token")

    result = __import__("asyncio").run(
        connect.cmd_scan(
            SimpleNamespace(json=True, non_interactive=False, timeout=0),
            storage,
        )
    )

    assert result == 0
    assert '"name": "truffle-container"' in capsys.readouterr().out


def test_grpc_address_preserves_explicit_ports_and_ipv6():
    from truffile.cli.connect import _grpc_address

    assert _grpc_address("10.0.0.2") == "10.0.0.2:80"
    assert _grpc_address("host:50051") == "host:50051"
    assert _grpc_address("[::1]:50051") == "[::1]:50051"
    assert _grpc_address("::1") == "[::1]:80"


def test_in_container_resolution_preserves_configured_grpc_port():
    from truffile.cli.connect import _resolve_connected_device

    storage = SimpleNamespace(
        _in_container_info=SimpleNamespace(
            device_name="truffle-container",
            grpc_address="127.0.0.1:50051",
        )
    )

    result = __import__("asyncio").run(_resolve_connected_device(storage))

    assert result == ("truffle-container", "127.0.0.1:50051")
