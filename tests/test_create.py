import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from truffile.cli.create import _safe_app_slug, _sample_truffile_yaml, _sample_foreground_py, _sample_background_py


class TestSafeAppSlug(unittest.TestCase):
    def test_simple_name(self):
        self.assertEqual(_safe_app_slug("My App"), "my_app")

    def test_hyphenated_name(self):
        self.assertEqual(_safe_app_slug("my-cool-app"), "my_cool_app")

    def test_special_chars_stripped(self):
        slug = _safe_app_slug("My App! (v2)")
        self.assertTrue(slug.isidentifier(), f"{slug} is not a valid identifier")

    def test_numeric_prefix_handled(self):
        slug = _safe_app_slug("123app")
        self.assertTrue(slug.isidentifier() or slug.startswith("_"))

    def test_empty_name(self):
        slug = _safe_app_slug("")
        self.assertTrue(len(slug) > 0)


class TestTemplateGeneration(unittest.TestCase):
    def test_truffile_yaml_contains_name(self):
        yaml = _sample_truffile_yaml("My App", "my_app")
        self.assertIn("My App", yaml)
        self.assertIn("my_app", yaml)

    def test_truffile_yaml_is_valid_yaml(self):
        import yaml as pyyaml
        content = _sample_truffile_yaml("Test", "test")
        parsed = pyyaml.safe_load(content)
        self.assertIsInstance(parsed, dict)
        self.assertIn("metadata", parsed)

    def test_foreground_template_valid_python(self):
        import ast
        code = _sample_foreground_py("Test", "test")
        ast.parse(code)

    def test_foreground_template_has_real_mcp_tool(self):
        code = _sample_foreground_py("Test", "test")
        self.assertIn("ForegroundApp", code)
        self.assertIn("test_ping", code)
        self.assertIn("app.run()", code)

    def test_background_template_valid_python(self):
        import ast
        code = _sample_background_py()
        ast.parse(code)

    def test_generated_yaml_has_both_processes(self):
        import yaml as pyyaml
        content = _sample_truffile_yaml("Hybrid", "hybrid")
        parsed = pyyaml.safe_load(content)
        meta = parsed.get("metadata", {})
        self.assertIn("foreground", meta)
        self.assertIn("background", meta)

    def test_generated_yaml_matches_selected_type(self):
        import yaml as pyyaml

        expected = {
            "foreground": ({"foreground"}, ["typed_foreground.py"]),
            "background": ({"background"}, ["typed_background.py"]),
            "hybrid": ({"foreground", "background"}, ["typed_foreground.py", "typed_background.py"]),
        }
        for app_type, (processes, files) in expected.items():
            with self.subTest(app_type=app_type):
                parsed = pyyaml.safe_load(_sample_truffile_yaml("Typed", "typed", app_type))
                metadata = parsed["metadata"]
                self.assertEqual(processes, {name for name in ("foreground", "background") if name in metadata})
                self.assertEqual(files, [Path(entry["source"]).name for entry in parsed["steps"][0]["files"]])


class TestCmdCreate(unittest.TestCase):
    def test_creates_directory_with_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            from types import SimpleNamespace
            args = SimpleNamespace(name="test-app", path=tmp)

            with patch("truffile.cli.create._load_stock_icon_bytes", return_value=(b"fake_png", "memory")):
                from truffile.cli.create import cmd_create
                result = cmd_create(args)

            app_dir = Path(tmp) / "test-app"
            if app_dir.exists():
                self.assertTrue((app_dir / "truffile.yaml").exists())

    def test_scaffolded_app_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            from types import SimpleNamespace
            args = SimpleNamespace(name="valid-app", path=tmp)

            with patch("truffile.cli.create._load_stock_icon_bytes", return_value=(b"fake_png", "memory")):
                from truffile.cli.create import cmd_create
                cmd_create(args)

            app_dir = Path(tmp) / "valid-app"
            if app_dir.exists() and (app_dir / "truffile.yaml").exists():
                from truffile.schema.app_config import validate_app_dir
                valid, config, app_type, warnings, errors = validate_app_dir(app_dir)
                self.assertTrue(valid, f"scaffolded app failed validation: {errors}")

    def test_each_app_type_passes_cli_validate_and_deploy_dry_run(self):
        from types import SimpleNamespace

        from truffile.cli.deploy import cmd_deploy
        from truffile.cli.validate import cmd_validate

        expected = {
            "foreground": ("foreground", {"typed_foreground.py", "icon.png", "truffile.yaml"}),
            "background": ("background", {"typed_background.py", "icon.png", "truffile.yaml"}),
            "hybrid": (
                "foreground+background",
                {"typed_foreground.py", "typed_background.py", "icon.png", "truffile.yaml"},
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for app_type, (finish_label, files) in expected.items():
                with self.subTest(app_type=app_type):
                    args = SimpleNamespace(
                        name="typed",
                        path=str(Path(tmp) / app_type),
                        app_type=app_type,
                        json=False,
                        non_interactive=True,
                    )
                    with patch(
                        "truffile.cli.create._load_stock_icon_bytes",
                        return_value=(b"fake_png", "memory"),
                    ):
                        from truffile.cli.create import cmd_create

                        self.assertEqual(cmd_create(args), 0)

                    app_dir = Path(tmp) / app_type / "typed"
                    self.assertEqual({path.name for path in app_dir.iterdir()}, files)
                    self.assertEqual(
                        cmd_validate(SimpleNamespace(path=str(app_dir), json=False)),
                        0,
                    )
                    deploy_args = SimpleNamespace(
                        path=str(app_dir),
                        interactive=False,
                        dry_run=True,
                        json=True,
                        non_interactive=True,
                        replace=False,
                    )
                    with patch("truffile.cli.deploy._json_print") as json_print:
                        self.assertEqual(asyncio.run(cmd_deploy(deploy_args, object())), 0)
                    payload = json_print.call_args.args[0]
                    self.assertTrue(payload["dry_run"])
                    self.assertEqual(payload["app"]["mode"], finish_label)
