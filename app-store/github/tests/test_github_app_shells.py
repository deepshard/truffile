from __future__ import annotations

import unittest
from unittest.mock import patch

from truffile.app_runtime.testing import AppHarness, FakeBackgroundRuntime
from bg_worker import CycleResult
from config import TOKEN_EXPORT_TOOL_NAME
from github_background import app as github_bg_app
from github_foreground import app as github_fg_app, reset_for_test, set_client

class _FakeRemoteClient:
    def list_tools(self) -> list[dict[str, object]]:
        return [
            {
                "name": "list_pull_requests",
                "description": "List pull requests from GitHub MCP.",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {
            "content": [{"type": "text", "text": f"stub:{name}"}],
            "structuredContent": {"name": name, "arguments": arguments},
            "isError": False,
        }

class _BackgroundWorkerStub:
    def __init__(self, results: list[CycleResult]) -> None:
        self._results = list(results)

    def verify(self) -> tuple[bool, str]:
        return True, "GitHub background verify OK (user=@octocat)"

    def run_cycle(self) -> CycleResult:
        if self._results:
            return self._results.pop(0)
        return CycleResult(summary=None, uris=[], priority=0, changed=False)

class TestGitHubAppShells(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reset_for_test()
        github_bg_app.reset_for_test()

    async def test_foreground_harness_runs_registered_tool(self) -> None:
        with patch.dict("os.environ", {"GITHUB_ACCESS_TOKEN": "gho_test_token"}, clear=False):
            set_client(_FakeRemoteClient())
            harness = AppHarness(fg_app=github_fg_app, logger_names=["github.foreground"])
            result = await harness.run_fg(
                calls=[
                    ("list_pull_requests", {"owner": "truffle-ai", "repo": "pyfw-codex"}),
                    (TOKEN_EXPORT_TOOL_NAME, {"confirm_user_consented": True, "target_app": "codex"}),
                ]
            )

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        self.assertEqual(result.tool_calls[0]["result"]["structuredContent"]["name"], "list_pull_requests")
        self.assertEqual(result.tool_calls[1]["result"]["structuredContent"]["access_token"], "gho_test_token")
        self.assertEqual(result.tool_calls[1]["result"]["structuredContent"]["source"], "github_access_token")
        tool_names = {tool["name"] for tool in github_fg_app.list_tools()}
        self.assertIn("list_pull_requests", tool_names)
        self.assertIn(TOKEN_EXPORT_TOOL_NAME, tool_names)

    async def test_background_harness_captures_submission(self) -> None:
        worker = _BackgroundWorkerStub(
            [
                CycleResult(
                    summary="GitHub activity digest (2026-03-23T00:00:00+00:00) for @octocat",
                    uris=["https://github.com/org/repo/pull/1"],
                    priority=1,
                    changed=True,
                )
            ]
        )
        with patch.object(github_bg_app, "build_worker", return_value=worker):
            harness = AppHarness(bg_app=github_bg_app, logger_names=["github.background"])
            result = await harness.run_bg(cycles=1)

        self.assertTrue(result.success)
        self.assertEqual(len(result.submissions), 1)
        self.assertIn("GitHub activity digest", result.submissions[0]["text"])

    async def test_background_runtime_reports_hard_auth_failure(self) -> None:
        worker = _BackgroundWorkerStub(
            [CycleResult(summary=None, uris=[], priority=0, changed=False, auth_error="bad credentials")]
        )
        with patch.object(github_bg_app, "build_worker", return_value=worker):
            runtime = FakeBackgroundRuntime(github_bg_app, cycles=1)
            runtime.run()

        self.assertEqual(len(runtime.all_reported_errors), 1)
        self.assertIn("GitHub authentication failure", runtime.all_reported_errors[0].error_message)

    async def test_background_runtime_records_cycles(self) -> None:
        worker = _BackgroundWorkerStub(
            [
                CycleResult(summary="Cycle 1", uris=[], priority=1, changed=True),
                CycleResult(summary=None, uris=[], priority=0, changed=False),
            ]
        )
        with patch.object(github_bg_app, "build_worker", return_value=worker):
            runtime = FakeBackgroundRuntime(github_bg_app, cycles=2)
            contexts = runtime.run()

        self.assertEqual(len(contexts), 2)
        self.assertEqual(contexts[0].run_num, 0)
        self.assertEqual(contexts[1].run_num, 1)
        submissions = runtime.all_submissions
        self.assertEqual(len(submissions), 1)
        self.assertEqual(submissions[0].text, "Cycle 1")

    async def test_background_cycle_closes_worker_before_run(self) -> None:
        worker = _BackgroundWorkerStub([CycleResult(summary=None, uris=[], priority=0, changed=False)])
        worker.close_calls = 0

        def _close() -> None:
            worker.close_calls += 1

        worker.close = _close  # type: ignore[attr-defined]

        with patch.object(github_bg_app, "build_worker", return_value=worker):
            runtime = FakeBackgroundRuntime(github_bg_app, cycles=1)
            runtime.run()

        self.assertGreaterEqual(worker.close_calls, 1)

if __name__ == "__main__":
    unittest.main()
