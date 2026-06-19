import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import yaml

from truffile.cli.obsidian import (
    _collect_bridge_config,
    _configure_staged_obsidian_manifest,
    _ensure_bridge_running,
    _list_managed_bridge_processes,
    _stage_obsidian_app,
    cmd_obsidian_deploy,
)
from truffile.storage import StorageService, StoredObsidianBridge, StoredState


class TestObsidianCli(unittest.TestCase):
    def _make_storage(self, tmp_dir: str) -> StorageService:
        storage = StorageService()
        storage.storage_dir = Path(tmp_dir)
        storage.state_file = Path(tmp_dir) / "state.json"
        storage.state = StoredState()
        return storage

    def test_collect_bridge_config_merges_overrides_into_existing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "vault"
            vault.mkdir()

            storage = self._make_storage(tmp)
            storage.set_obsidian_bridge(
                StoredObsidianBridge(
                    vault_path=str(vault),
                    token="existing-token",
                    advertise_host="10.0.0.5",
                    port=27125,
                    bind_host="0.0.0.0",
                )
            )

            config = _collect_bridge_config(storage, port=28000)

            self.assertEqual(str(config.vault_path), str(vault.resolve()))
            self.assertEqual(config.token, "existing-token")
            self.assertEqual(config.advertise_host, "10.0.0.5")
            self.assertEqual(config.bind_host, "0.0.0.0")
            self.assertEqual(config.port, 28000)

    def test_collect_bridge_config_can_replace_existing_vault_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_vault = Path(tmp) / "old-vault"
            new_vault = Path(tmp) / "new-vault"
            old_vault.mkdir()
            new_vault.mkdir()

            storage = self._make_storage(tmp)
            storage.set_obsidian_bridge(
                StoredObsidianBridge(
                    vault_path=str(old_vault),
                    token="existing-token",
                    advertise_host="10.0.0.5",
                    port=27125,
                    bind_host="0.0.0.0",
                )
            )

            config = _collect_bridge_config(storage, raw_vault=str(new_vault))

            self.assertEqual(str(config.vault_path), str(new_vault.resolve()))
            self.assertEqual(config.token, "existing-token")

    def test_stage_obsidian_app_fetches_public_files_when_using_default_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            payloads = {
                "truffile.yaml": b"metadata:\n  name: obsidian\n",
                "bridge_client.py": b"print('bridge')\n",
                "obsidian_foreground.py": b"print('fg')\n",
                "icon.png": b"\x89PNG\r\n",
            }

            def fake_fetch(url: str, *, timeout: float = 15.0) -> bytes:
                return payloads[url.rsplit("/", 1)[-1]]

            with patch("truffile.cli.obsidian._fetch_bytes", side_effect=fake_fetch):
                app_dir = _stage_obsidian_app(Path(tmp), None)

            self.assertTrue((app_dir / "truffile.yaml").exists())
            self.assertEqual((app_dir / "bridge_client.py").read_bytes(), payloads["bridge_client.py"])
            self.assertEqual((app_dir / "obsidian_foreground.py").read_bytes(), payloads["obsidian_foreground.py"])
            self.assertEqual((app_dir / "icon.png").read_bytes(), payloads["icon.png"])

    def test_stage_obsidian_app_uses_explicit_local_path_when_provided(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "truffile.yaml").write_text("metadata:\n  name: obsidian\n", encoding="utf-8")
            (source / "bridge_client.py").write_text("print('bridge')\n", encoding="utf-8")
            (source / "obsidian_foreground.py").write_text("print('fg')\n", encoding="utf-8")
            (source / "icon.png").write_bytes(b"\x89PNG\r\n")

            app_dir = _stage_obsidian_app(root / "tmp", str(source))

            self.assertTrue((app_dir / "truffile.yaml").exists())
            self.assertEqual((app_dir / "bridge_client.py").read_text(encoding="utf-8"), "print('bridge')\n")

    def test_configure_staged_manifest_injects_bridge_env_and_removes_bridge_text_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "truffile.yaml"
            manifest_path.write_text(
                """
metadata:
  name: Obsidian
  foreground:
    process:
      environment:
        PYTHONUNBUFFERED: "1"
steps:
  - name: Copy application files
    type: files
    files: []
  - name: Configure Obsidian bridge
    type: text
    fields:
      - name: obsidian_bridge_base_url
        env: OBSIDIAN_BRIDGE_BASE_URL
      - name: obsidian_bridge_token
        env: OBSIDIAN_BRIDGE_TOKEN
  - name: Other config
    type: text
    fields:
      - name: other
        env: OTHER_ENV
""",
                encoding="utf-8",
            )
            config = SimpleNamespace(
                advertise_host="10.0.0.5",
                port=27125,
                token="secret-token",
            )

            _configure_staged_obsidian_manifest(manifest_path, config)

            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            env = manifest["metadata"]["foreground"]["process"]["environment"]
            self.assertEqual(env["OBSIDIAN_BRIDGE_BASE_URL"], "http://10.0.0.5:27125")
            self.assertEqual(env["OBSIDIAN_BRIDGE_TOKEN"], "secret-token")
            self.assertEqual([step["name"] for step in manifest["steps"]], ["Copy application files", "Other config"])

    def test_list_managed_bridge_processes_filters_for_obsidian_serve(self):
        ps_output = "\n".join(
            [
                "123 /usr/bin/python -c import sys; from truffile.cli import main; sys.argv=['truffile']; raise SystemExit(main()) obsidian serve",
                "124 python other_script.py",
                "125 truffile chat hello",
            ]
        )
        with patch("truffile.cli.obsidian.os.getpid", return_value=999), patch(
            "truffile.cli.obsidian.subprocess.run"
        ) as run:
            run.return_value = SimpleNamespace(returncode=0, stdout=ps_output)
            managed = _list_managed_bridge_processes()

        self.assertEqual(managed, [(123, "/usr/bin/python -c import sys; from truffile.cli import main; sys.argv=['truffile']; raise SystemExit(main()) obsidian serve")])

    def test_ensure_bridge_running_always_restarts_via_start(self):
        storage = object()
        config = SimpleNamespace()
        with patch("truffile.cli.obsidian._start_bridge_background") as start_bridge_background:
            _ensure_bridge_running(storage=storage, config=config)
        start_bridge_background.assert_called_once_with(storage, config)


class TestObsidianDeploy(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_does_not_start_bridge_or_probe_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "obsidian"
            app_dir.mkdir()
            (app_dir / "truffile.yaml").write_text("metadata:\n  name: obsidian\n", encoding="utf-8")

            args = SimpleNamespace(
                path="obsidian",
                shell=False,
                interactive=False,
                dry_run=True,
                no_finalize=False,
                vault=None,
                pick_vault=False,
                advertise_host=None,
                bind_host=None,
                port=None,
                token=None,
                obsidian_reconfigure=False,
            )
            config = SimpleNamespace(
                vault_path=Path("/tmp/vault"),
                token="secret-token",
                advertise_host="10.0.0.5",
                port=27125,
                bind_host="0.0.0.0",
            )

            with patch("truffile.cli.obsidian._collect_bridge_config", return_value=config), patch(
                "truffile.cli.obsidian._ensure_bridge_running"
            ) as ensure_bridge_running, patch(
                "truffile.cli.obsidian._probe_bridge_from_device", new_callable=AsyncMock
            ) as probe_bridge_from_device, patch(
                "truffile.cli.obsidian._stage_obsidian_app", return_value=app_dir
            ), patch(
                "truffile.cli.deploy.cmd_deploy", new_callable=AsyncMock, return_value=0
            ) as cmd_deploy:
                result = await cmd_obsidian_deploy(args, storage=object())

        self.assertEqual(result, 0)
        ensure_bridge_running.assert_not_called()
        probe_bridge_from_device.assert_not_called()
        cmd_deploy.assert_awaited_once()
