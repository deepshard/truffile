import tempfile
import unittest
from pathlib import Path

from truffile.deploy.builder import (
    build_deploy_plan,
    _normalize_cmd,
    _bundle_id_from_name,
    _env_map_to_list,
)


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
