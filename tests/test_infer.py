import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from shlex import quote as shlex_quote
from types import SimpleNamespace

from truffile.cli import infer as infer_cli
from truffile.cli.infer import (
    _attachment_buffer_prefix,
    _attachment_labels,
    _consume_inline_dragged_image_sources,
    _strip_attachment_tokens,
)
from truffile.cli.models import _pick_default_model


class TestInferAttachments(unittest.TestCase):
    def test_attachment_labels_include_image_numbers(self):
        labels = _attachment_labels(
            [
                "path=/tmp/My File.png size=12.3 KiB mime=image/png",
                "url=https://example.com/cat.png size=6.0 KiB mime=image/png",
            ]
        )
        self.assertEqual(labels[0], "[Image #1] My File.png")
        self.assertEqual(labels[1], "[Image #2] url")

    def test_attachment_buffer_prefix_formats_tokens_for_prompt_bar(self):
        prefix = _attachment_buffer_prefix(
            [
                "path=/tmp/My File.png size=12.3 KiB mime=image/png",
                "url=https://example.com/cat.png size=6.0 KiB mime=image/png",
            ]
        )
        self.assertEqual(prefix, "[Image #1] [Image #2] ")

    def test_consume_inline_dragged_image_sources_accepts_single_local_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "photo.png"
            image_path.write_bytes(b"fake")
            dragged, remaining = _consume_inline_dragged_image_sources(str(image_path))
        self.assertEqual(dragged, [str(image_path)])
        self.assertEqual(remaining, "")

    def test_consume_inline_dragged_image_sources_accepts_shell_escaped_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "my photo.png"
            image_path.write_bytes(b"fake")
            dragged, remaining = _consume_inline_dragged_image_sources(str(image_path).replace(" ", "\\ "))
        self.assertEqual(dragged, [str(image_path)])
        self.assertEqual(remaining, "")

    def test_consume_inline_dragged_image_sources_splits_path_from_prompt_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "photo.png"
            image_path.write_bytes(b"fake")
            dragged, remaining = _consume_inline_dragged_image_sources(
                f"{shlex_quote(str(image_path))} describe this image plz"
            )
        self.assertEqual(dragged, [str(image_path)])
        self.assertEqual(remaining, "describe this image plz")

    def test_consume_inline_dragged_image_sources_rejects_non_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "notes.txt"
            file_path.write_text("hello", encoding="utf-8")
            dragged, remaining = _consume_inline_dragged_image_sources(str(file_path))
        self.assertEqual(dragged, [])
        self.assertEqual(remaining, str(file_path))

    def test_strip_attachment_tokens_removes_prompt_labels(self):
        raw = "[Image #1] [Image #2] can u see this image?"
        self.assertEqual(_strip_attachment_tokens(raw), "can u see this image?")


class TestDefaultModelSelection(unittest.TestCase):
    def test_pick_default_model_prefers_qwen_35b(self):
        models = [
            {"id": "foo-small", "name": "Foo 7B"},
            {"id": "bar-large", "name": "Bar 70B"},
            {"id": "qwen35b", "name": "Qwen 3.6 35B"},
        ]
        default = _pick_default_model(models)
        assert default is not None
        self.assertEqual(default["id"], "qwen35b")

    def test_pick_default_model_falls_back_to_sorted_first(self):
        models = [
            {"id": "zeta", "name": "Zeta"},
            {"id": "alpha", "name": "Alpha"},
        ]
        default = _pick_default_model(models)
        assert default is not None
        self.assertEqual(default["id"], "alpha")


def test_oneshot_json_reports_default_model_failure(monkeypatch, capsys):
    async def resolve_device(storage, requested_device=None, *, emit_errors=True):
        return "truffle-1234", "127.0.0.1"

    async def no_default_model(ip):
        return None

    monkeypatch.setattr(infer_cli, "_resolve_connected_device", resolve_device)
    monkeypatch.setattr(infer_cli, "_default_model", no_default_model)
    args = SimpleNamespace(
        json=True,
        quiet=True,
        list_models=False,
        model=None,
        timeout=None,
    )

    result = asyncio.run(infer_cli._run_oneshot(args, object()))
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["error"] == {
        "code": "execution_error",
        "message": "failed to resolve default model from IF2",
    }
    assert payload["device"] == "truffle-1234"
