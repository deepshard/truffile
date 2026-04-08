from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from test_support import install_repo_paths, install_stub_modules

install_repo_paths()
install_stub_modules()

from arxiv_bg_worker import ArxivBackgroundWorker, ArxivRecommendation
from arxiv_common import parse_research_interests


class TestArxivUnit(unittest.TestCase):
    def test_parse_research_interests_dedupes_and_preserves_order(self) -> None:
        raw = "LLM safety, multi-agent systems, llm safety,  , retrieval"
        self.assertEqual(
            parse_research_interests(raw),
            ["LLM safety", "multi-agent systems", "retrieval"],
        )

    def test_background_verify_requires_interest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                "os.environ",
                {"ARXIV_BG_STATE_PATH": f"{tmpdir}/state.json"},
                clear=False,
            ):
                worker = ArxivBackgroundWorker(interests_raw="")
                ok, message = worker.verify()

        self.assertFalse(ok)
        self.assertIn("No research interests configured", message)

    def test_background_context_includes_paper_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                "os.environ",
                {"ARXIV_BG_STATE_PATH": f"{tmpdir}/state.json"},
                clear=False,
            ):
                worker = ArxivBackgroundWorker(interests_raw="language models")
                text = worker._build_context(
                    [
                        ArxivRecommendation(
                            interest="language models",
                            paper_id="2501.01234",
                            title="Compact Reasoning Models",
                            published="2025-01-02",
                            abs_url="https://arxiv.org/abs/2501.01234",
                            summary="A short abstract snippet.",
                        )
                    ]
                )

        self.assertIn("Compact Reasoning Models", text)
        self.assertIn("2501.01234", text)
        self.assertIn("language models", text)


if __name__ == "__main__":
    unittest.main()
