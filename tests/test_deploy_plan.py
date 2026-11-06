import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from truffile.deploy.builder import deploy_with_builder
from truffile.deploy.plan import (
    build_deploy_plan,
    _normalize_cmd,
    _bundle_id_from_name,
    _env_map_to_list,
)
from truffile.deploy.steps.files import handle_files


class TestNormalizeCmd(unittest.TestCase):
    def test_list_passthrough(self):
        result = _normalize_cmd(["python", "app.py"])
        # returns (binary, args) tuple
        self.assertIsNotNone(result)
        binary = result[0] if isinstance(result, tuple) else result
        self.assertIn("python", str(binary))

    def test_string_input(self):
        result = _normalize_cmd("python app.py")
        self.assertIsNotNone(result)

    def test_empty_list(self):
        binary, args = _normalize_cmd([])
        self.assertEqual(binary, "")
        self.assertEqual(args, [])


class TestBundleIdFromName(unittest.TestCase):
    def test_simple_name(self):
        bid = _bundle_id_from_name("My App")
        self.assertIsInstance(bid, str)
        self.assertFalse(" " in bid)

    def test_special_chars_removed(self):
        bid = _bundle_id_from_name("My App! (v2)")
        self.assertFalse("!" in bid)
        self.assertFalse("(" in bid)


class TestEnvMapToList(unittest.TestCase):
    def test_converts_dict(self):
        result = _env_map_to_list({"KEY": "value", "FOO": "bar"})
        self.assertIsInstance(result, list)
        joined = " ".join(result)
        self.assertIn("KEY", joined)
        self.assertIn("value", joined)

    def test_empty_dict(self):
        result = _env_map_to_list({})
        self.assertEqual(len(result), 0)

    def test_none_input(self):
        result = _env_map_to_list(None)
        self.assertEqual(len(result), 0)


class TestBuildDeployPlan(unittest.TestCase):
    def _make_app_dir(self, tmp: str, yaml_content: str, files: dict[str, str] | None = None) -> Path:
        app_dir = Path(tmp) / "test-app"
        app_dir.mkdir()
        (app_dir / "truffile.yaml").write_text(yaml_content)
        for name, content in (files or {}).items():
            (app_dir / name).write_text(content)
        return app_dir

    def test_foreground_only(self):
        config = {
            "metadata": {
                "name": "FG App",
                "bundle_id": "org.test.fg",
                "description": "FG only",
                "foreground": {
                    "process": {"cmd": ["python", "fg.py"]},
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = self._make_app_dir(tmp, "", {"fg.py": "pass"})
            plan = build_deploy_plan(config=config, app_dir=app_dir, app_type="focus")
            self.assertIsNotNone(plan)

    def test_background_only(self):
        config = {
            "metadata": {
                "name": "BG App",
                "bundle_id": "org.test.bg",
                "description": "BG only",
                "background": {
                    "process": {"cmd": ["python", "bg.py"]},
                    "default_schedule": {"type": "interval", "interval": {"duration": "30m"}},
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = self._make_app_dir(tmp, "", {"bg.py": "pass"})
            plan = build_deploy_plan(config=config, app_dir=app_dir, app_type="ambient")
            self.assertIsNotNone(plan)


class _NoopSpinner:
    def __init__(self, *_args, **_kwargs):
        pass

    def start(self):
        pass

    def stop(self, success=True):
        pass

    def fail(self, _message=None):
        pass


class _NoopLog:
    def __init__(self, *_args, **_kwargs):
        pass

    def add(self, _line):
        pass

    def finish(self):
        pass


class TestDeployWithBuilder(unittest.IsolatedAsyncioTestCase):
    async def test_discards_build_session_when_step_fails(self):
        class FakeClient:
            def __init__(self):
                self.app_uuid = None
                self.access_path = None
                self.discarded = False

            async def connect(self):
                pass

            async def start_build(self):
                self.app_uuid = "app-uuid"
                self.access_path = "route-token"

            async def exec(self, _cmd, cwd="/"):
                return SimpleNamespace(exit_code=0)

            async def upload(self, _src, _dest):
                raise RuntimeError("upload failed")

            async def discard(self):
                self.discarded = True
                self.app_uuid = None
                self.access_path = None

        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "test-app"
            app_dir.mkdir()
            (app_dir / "app.py").write_text("pass", encoding="utf-8")
            config = {
                "metadata": {
                    "name": "FG App",
                    "bundle_id": "org.test.fg",
                    "foreground": {
                        "process": {"cmd": ["python", "app.py"]},
                    },
                },
                "steps": [
                    {
                        "name": "Copy",
                        "type": "files",
                        "files": [{"source": "./app.py", "destination": "./app.py"}],
                    }
                ],
            }
            client = FakeClient()

            with self.assertRaisesRegex(RuntimeError, "upload failed"):
                await deploy_with_builder(
                    client=client,
                    config=config,
                    app_dir=app_dir,
                    app_type="focus",
                    device="truffle-test",
                    interactive=False,
                    spinner_cls=_NoopSpinner,
                    scrolling_log_cls=_NoopLog,
                    info=lambda _msg: None,
                    success=lambda _msg: None,
                    error=lambda _msg: None,
                    color_dim="",
                    color_reset="",
                    color_bold="",
                    arrow="->",
                    interactive_shell=lambda _url: None,
                )

        self.assertTrue(client.discarded)
        self.assertIsNone(client.app_uuid)


class TestFileSteps(unittest.IsolatedAsyncioTestCase):
    async def test_directory_upload_rejects_external_symlink(self):
        class FakeClient:
            async def upload(self, _src, _dest):
                raise AssertionError("external symlink should not be uploaded")

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app_dir = base / "test-app"
            source_dir = app_dir / "files"
            source_dir.mkdir(parents=True)
            outside = base / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            link = source_dir / "linked.txt"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")

            with self.assertRaisesRegex(ValueError, "Source file must stay within"):
                await handle_files(
                    {
                        "files": [
                            {
                                "source": "./files",
                                "destination": "./files",
                            }
                        ]
                    },
                    client=FakeClient(),
                    app_dir=app_dir,
                    spinner_cls=_NoopSpinner,
                    arrow="->",
                    color_dim="",
                    color_reset="",
                )
