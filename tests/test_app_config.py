import tempfile
import unittest
from pathlib import Path

from truffile.schema.app_config import validate_app_dir


class TestValidateAppDir(unittest.TestCase):
    def _make_app(self, tmp: str, yaml_content: str, files: dict[str, str] | None = None):
        app_dir = Path(tmp) / "test-app"
        app_dir.mkdir()
        (app_dir / "truffile.yaml").write_text(yaml_content)
        for name, content in (files or {}).items():
            p = app_dir / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        return app_dir

    def test_valid_foreground_app(self):
        yaml = """
metadata:
  name: Test App
  bundle_id: org.test.app
  description: A test app
  foreground:
    process:
      cmd: [python, app.py]
steps:
  - name: Copy files
    type: files
    files:
      - source: ./app.py
        destination: ./app.py
"""
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = self._make_app(tmp, yaml, {"app.py": "print('hello')"})
            valid, config, app_type, warnings, errors = validate_app_dir(app_dir)
            self.assertTrue(valid, f"errors: {errors}")

    def test_missing_truffile_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = Path(tmp) / "empty-app"
            app_dir.mkdir()
            valid, config, app_type, warnings, errors = validate_app_dir(app_dir)
            self.assertFalse(valid)
            self.assertTrue(any("truffile.yaml" in e.lower() or "not found" in e.lower() for e in errors))

    def test_invalid_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = self._make_app(tmp, "{{{{invalid yaml::::")
            valid, config, app_type, warnings, errors = validate_app_dir(app_dir)
            self.assertFalse(valid)

    def test_missing_metadata_name(self):
        yaml = """
metadata:
  bundle_id: org.test.app
  foreground:
    process:
      cmd: [python, app.py]
"""
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = self._make_app(tmp, yaml)
            valid, config, app_type, warnings, errors = validate_app_dir(app_dir)
            self.assertFalse(valid)

    def test_missing_process_config(self):
        yaml = """
metadata:
  name: No Process App
  bundle_id: org.test.noprocess
  description: No fg or bg
"""
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = self._make_app(tmp, yaml)
            valid, config, app_type, warnings, errors = validate_app_dir(app_dir)
            self.assertFalse(valid)

    def test_hybrid_app_type(self):
        yaml = """
metadata:
  name: Hybrid
  bundle_id: org.test.hybrid
  description: Both fg and bg
  foreground:
    process:
      cmd: [python, fg.py]
  background:
    process:
      cmd: [python, bg.py]
    default_schedule:
      type: interval
      interval:
        duration: 30m
steps:
  - name: Copy
    type: files
    files:
      - source: ./fg.py
        destination: ./fg.py
      - source: ./bg.py
        destination: ./bg.py
"""
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = self._make_app(tmp, yaml, {"fg.py": "pass", "bg.py": "pass"})
            valid, config, app_type, warnings, errors = validate_app_dir(app_dir)
            self.assertTrue(valid, f"errors: {errors}")
            self.assertEqual(app_type, "hybrid")

    def test_bad_python_syntax_detected(self):
        yaml = """
metadata:
  name: Bad Syntax
  bundle_id: org.test.badsyntax
  foreground:
    process:
      cmd: [python, broken.py]
steps:
  - name: Copy
    type: files
    files:
      - source: ./broken.py
        destination: ./broken.py
"""
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = self._make_app(tmp, yaml, {"broken.py": "def foo(\n  pass"})
            valid, config, app_type, warnings, errors = validate_app_dir(app_dir)
            # should have a warning about syntax
            all_messages = warnings + errors
            has_syntax = any("syntax" in m.lower() for m in all_messages)
            self.assertTrue(has_syntax, f"expected syntax warning in: {all_messages}")

    def test_missing_source_file(self):
        yaml = """
metadata:
  name: Missing File
  bundle_id: org.test.missing
  foreground:
    process:
      cmd: [python, app.py]
steps:
  - name: Copy
    type: files
    files:
      - source: ./app.py
        destination: ./app.py
"""
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = self._make_app(tmp, yaml)
            # app.py not created — should warn or error
            valid, config, app_type, warnings, errors = validate_app_dir(app_dir)
            all_messages = warnings + errors
            has_missing = any("not found" in m.lower() or "missing" in m.lower() or "does not exist" in m.lower() for m in all_messages)
            self.assertTrue(has_missing, f"expected missing file message in: {all_messages}")

    def test_source_outside_app_is_rejected(self):
        yaml = """
metadata:
  name: External Source
  bundle_id: org.test.external
  foreground:
    process:
      cmd: [python, app.py]
steps:
  - name: Copy
    type: files
    files:
      - source: ../secret.txt
        destination: ./secret.txt
"""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "secret.txt").write_text("secret")
            app_dir = self._make_app(tmp, yaml, {"app.py": "pass"})
            valid, _config, _app_type, _warnings, errors = validate_app_dir(app_dir)

            self.assertFalse(valid)
            self.assertTrue(any("source file must stay within" in error.lower() for error in errors))

    def test_external_icon_is_rejected(self):
        yaml = """
metadata:
  name: External Icon
  bundle_id: org.test.external-icon
  icon_file: ../icon.png
  foreground:
    process:
      cmd: [python, app.py]
"""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "icon.png").write_text("not an app icon")
            app_dir = self._make_app(tmp, yaml, {"app.py": "pass"})
            valid, _config, _app_type, _warnings, errors = validate_app_dir(app_dir)

            self.assertFalse(valid)
            self.assertTrue(any("icon file must stay within" in error.lower() for error in errors))

    def test_source_directory_with_external_symlink_is_rejected(self):
        yaml = """
metadata:
  name: Linked Source
  bundle_id: org.test.linked-source
  foreground:
    process:
      cmd: [python, app.py]
steps:
  - name: Copy
    type: files
    files:
      - source: ./files
        destination: ./files
"""
        with tempfile.TemporaryDirectory() as tmp:
            app_dir = self._make_app(tmp, yaml, {"app.py": "pass"})
            source_dir = app_dir / "files"
            source_dir.mkdir()
            outside = Path(tmp, "secret.txt")
            outside.write_text("secret", encoding="utf-8")
            try:
                (source_dir / "linked.txt").symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")

            valid, _config, _app_type, _warnings, errors = validate_app_dir(app_dir)

            self.assertFalse(valid)
            self.assertTrue(any("source file must stay within" in error.lower() for error in errors))

    def test_vnc_step_is_rejected_before_deploy(self):
        for step_type in ("vnc",):
            yaml = f"""
metadata:
  name: Unsupported Step
  bundle_id: org.test.unsupported
  foreground:
    process:
      cmd: [python, app.py]
steps:
  - name: Unsupported
    type: {step_type}
"""
            with self.subTest(step_type=step_type), tempfile.TemporaryDirectory() as tmp:
                app_dir = self._make_app(tmp, yaml, {"app.py": "pass"})
                valid, _config, _app_type, _warnings, errors = validate_app_dir(app_dir)

                self.assertFalse(valid)
                self.assertTrue(errors)
