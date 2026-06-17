from __future__ import annotations

import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from test_support import install_repo_paths, install_stub_modules

install_repo_paths()
install_stub_modules()

import arxiv_tools
from app_store_runtime import AppHarness, FakeBackgroundRuntime
from arxiv_background import app as arxiv_bg_app
from arxiv_bg_worker import BgRunResult
from arxiv_foreground import app as arxiv_fg_app


class TestArxivAppShells(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addAsyncCleanup(self._cleanup_tmpdir)
        self._env_patch = patch.dict(
            "os.environ",
            {
                "ARXIV_RESEARCH_INTERESTS": "language models",
                "ARXIV_BG_STATE_PATH": f"{self._tmpdir.name}/state.json",
            },
            clear=False,
        )
        self._env_patch.start()
        self.addAsyncCleanup(self._stop_env_patch)
        arxiv_bg_app.reset_for_test()

    async def _cleanup_tmpdir(self) -> None:
        self._tmpdir.cleanup()

    async def _stop_env_patch(self) -> None:
        self._env_patch.stop()

    async def test_foreground_harness_runs_registered_tool(self) -> None:
        with patch.object(
            arxiv_tools,
            "search_papers",
            new=AsyncMock(
                return_value={
                    "status": "success",
                    "total_results": 1,
                    "papers": [{"id": "2501.01234", "title": "Compact Reasoning Models"}],
                }
            ),
        ):
            harness = AppHarness(
                fg_app=arxiv_fg_app,
                logger_names=["arxiv.foreground", "arxiv.tools"],
            )
            result = await harness.run_fg(
                calls=[
                    (
                        "search_papers",
                        {
                            "query": "compact reasoning models",
                            "max_results": 1,
                        },
                    )
                ]
            )

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        self.assertEqual(result.tool_calls[0]["tool"], "search_papers")
        self.assertEqual(result.tool_calls[0]["result"]["papers"][0]["id"], "2501.01234")
        self.assertIn("search_papers", {tool["name"] for tool in arxiv_fg_app.list_tools()})
        self.assertIn("deep-paper-analysis", {prompt["name"] for prompt in arxiv_fg_app.list_prompts()})

    async def test_background_harness_captures_submission(self) -> None:
        with patch.object(
            arxiv_bg_app,
            "run_cycle",
            return_value=BgRunResult(
                content="Recent arXiv papers\n- Compact Reasoning Models",
                error=None,
            ),
        ):
            harness = AppHarness(
                bg_app=arxiv_bg_app,
                logger_names=["arxiv.background", "arxiv.bg_worker"],
            )
            result = await harness.run_bg(cycles=1)

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        self.assertEqual(len(result.submissions), 1)
        self.assertIn("Compact Reasoning Models", result.submissions[0]["text"])

    async def test_background_runtime_records_cycles(self) -> None:
        with patch.object(
            arxiv_bg_app,
            "run_cycle",
            side_effect=[
                BgRunResult(content="Cycle 1", error=None),
                BgRunResult(content="", error=None),
            ],
        ):
            runtime = FakeBackgroundRuntime(arxiv_bg_app, cycles=2)
            contexts = runtime.run()

        self.assertEqual(len(contexts), 2)
        self.assertEqual(contexts[0].run_num, 0)
        self.assertEqual(contexts[1].run_num, 1)
        submissions = runtime.all_submissions
        self.assertEqual(len(submissions), 1)
        self.assertEqual(submissions[0].text, "Cycle 1")

    async def test_background_harness_surfaces_reported_errors(self) -> None:
        with patch.object(arxiv_bg_app, "run_cycle", side_effect=RuntimeError("boom")):
            harness = AppHarness(
                bg_app=arxiv_bg_app,
                logger_names=["arxiv.background", "arxiv.bg_worker"],
            )
            result = await harness.run_bg(cycles=1)

        self.assertFalse(result.success)
        self.assertTrue(result.errors)
        self.assertIn("boom", result.errors[0])


if __name__ == "__main__":
    unittest.main()
