from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch


_app_dir = Path(__file__).resolve().parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from truffile.app_runtime import AppAuthError
from truffile.app_runtime.testing import AppHarness, FakeBackgroundRuntime

from whoop_background import app as whoop_bg_app
from whoop_bg_worker import BgRunResult, PreparedSubmission
from whoop_foreground import WhoopForegroundApp


class _BackgroundWorkerStub:
    def __init__(self, results: list[BgRunResult]) -> None:
        self._results = list(results)
        self.close_calls = 0

    async def verify(self) -> tuple[bool, str]:
        return True, "WHOOP background verify OK"

    async def run_cycle(self) -> BgRunResult:
        if self._results:
            return self._results.pop(0)
        return BgRunResult()

    async def close(self) -> None:
        self.close_calls += 1


class _ForegroundClientStub:
    async def verify(self) -> tuple[bool, str]:
        return False, "WHOOP access token is missing"

    async def close(self) -> None:
        return None


class TestWhoopAppShells(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        whoop_bg_app.reset_for_test()

    async def asyncTearDown(self) -> None:
        whoop_bg_app.reset_for_test()

    async def test_background_harness_captures_submission(self) -> None:
        worker = _BackgroundWorkerStub(
            [
                BgRunResult(
                    submissions=[
                        PreparedSubmission(
                            text="WHOOP recovery scored: 72% recovery, RHR 54 bpm.",
                            priority=1,
                        )
                    ]
                )
            ]
        )

        with patch.object(whoop_bg_app, "build_worker", return_value=worker):
            harness = AppHarness(bg_app=whoop_bg_app, logger_names=["whoop.background"])
            result = await harness.run_bg(cycles=1)

        self.assertTrue(result.success)
        self.assertEqual(len(result.submissions), 1)
        self.assertIn("WHOOP recovery scored", result.submissions[0]["text"])

    async def test_background_runtime_reports_repeated_auth_failure(self) -> None:
        worker = _BackgroundWorkerStub(
            [
                BgRunResult(auth_error="WHOOP rejected the installed credentials"),
                BgRunResult(auth_error="WHOOP rejected the installed credentials"),
                BgRunResult(auth_error="WHOOP rejected the installed credentials"),
            ]
        )

        with patch.object(whoop_bg_app, "build_worker", return_value=worker):
            runtime = FakeBackgroundRuntime(whoop_bg_app, cycles=3)
            runtime.run()

        self.assertEqual(len(runtime.all_reported_errors), 1)
        self.assertIn("whoop authentication failure", runtime.all_reported_errors[0].error_message)

    async def test_reset_for_test_closes_worker(self) -> None:
        worker = _BackgroundWorkerStub([BgRunResult()])

        with patch.object(whoop_bg_app, "build_worker", return_value=worker):
            runtime = FakeBackgroundRuntime(whoop_bg_app, cycles=1)
            runtime.run()

        whoop_bg_app.reset_for_test()

        self.assertGreaterEqual(worker.close_calls, 1)

    async def test_foreground_status_raises_auth_error_for_missing_token(self) -> None:
        app = WhoopForegroundApp(client=_ForegroundClientStub())  # type: ignore[arg-type]

        with patch.object(app._error_reporter, "report_foreground_exception", new=AsyncMock()):
            with self.assertRaisesRegex(AppAuthError, "WHOOP access token is missing"):
                await app.invoke_tool("whoop_status")

    async def test_foreground_bad_limit_returns_tool_error(self) -> None:
        app = WhoopForegroundApp(client=_ForegroundClientStub())  # type: ignore[arg-type]

        result = await app.invoke_tool("list_sleep", limit=0)

        self.assertEqual(result["status"], "error")
        self.assertIn("limit must be between 1 and 25", result["message"])


if __name__ == "__main__":
    unittest.main()
