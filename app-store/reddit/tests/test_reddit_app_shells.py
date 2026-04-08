from __future__ import annotations

import unittest
from unittest.mock import patch

from truffile.app_runtime.testing import AppHarness, FakeBackgroundRuntime
from reddit_background import app as reddit_bg_app
from reddit_bg_worker import BgRunResult, PreparedSubmission

class TestRedditAppShells(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reddit_bg_app.reset_for_test()

    async def test_background_harness_captures_submission(self) -> None:
        with patch.object(
            reddit_bg_app,
            "run_cycle",
            return_value=BgRunResult(
                submissions=[
                    PreparedSubmission(
                        text="From Reddit: **news** example.com 123 points, 8 comments",
                        uris=("https://example.com/story",),
                    )
                ]
            ),
        ):
            harness = AppHarness(
                bg_app=reddit_bg_app,
                logger_names=["reddit.background", "reddit.bg_worker"],
            )
            result = await harness.run_bg(cycles=1)

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        self.assertEqual(len(result.submissions), 1)
        self.assertIn("From Reddit:", result.submissions[0]["text"])

    async def test_background_runtime_records_cycles(self) -> None:
        with patch.object(
            reddit_bg_app,
            "run_cycle",
            side_effect=[
                BgRunResult(submissions=[PreparedSubmission(text="Cycle 1", uris=())]),
                BgRunResult(submissions=[]),
            ],
        ):
            runtime = FakeBackgroundRuntime(reddit_bg_app, cycles=2)
            contexts = runtime.run()

        self.assertEqual(len(contexts), 2)
        self.assertEqual(contexts[0].run_num, 0)
        self.assertEqual(contexts[1].run_num, 1)
        submissions = runtime.all_submissions
        self.assertEqual(len(submissions), 1)
        self.assertEqual(submissions[0].text, "Cycle 1")

    async def test_background_harness_surfaces_reported_errors(self) -> None:
        with patch.object(reddit_bg_app, "run_cycle", side_effect=RuntimeError("reddit boom")):
            harness = AppHarness(
                bg_app=reddit_bg_app,
                logger_names=["reddit.background", "reddit.bg_worker"],
            )
            result = await harness.run_bg(cycles=1)

        self.assertFalse(result.success)
        self.assertTrue(result.errors)
        self.assertIn("reddit boom", result.errors[0])

if __name__ == "__main__":
    unittest.main()
