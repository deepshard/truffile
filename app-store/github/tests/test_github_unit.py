from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from auth import GitHubAuth
from bg_worker import CycleResult, GitHubBackgroundWorker, OrgActivity, SearchResult
from github_foreground import GitHubRemoteMcpClient


class TestGitHubAuth(unittest.TestCase):
    def test_load_access_token_reads_env(self) -> None:
        with patch.dict(os.environ, {"GITHUB_ACCESS_TOKEN": "gho_env_token"}, clear=False):
            self.assertEqual(GitHubAuth().load_access_token(), "gho_env_token")

    def test_missing_env_raises(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACCESS_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                GitHubAuth().load_access_token()


class TestGitHubRemoteMcpClient(unittest.TestCase):
    def test_list_tools_initializes_session_first(self) -> None:
        calls: list[str] = []

        def fake_post_jsonrpc(remote_url, payload, *, default_headers, session_id=None, timeout=30):
            del remote_url, default_headers, timeout
            method = str(payload.get("method", ""))
            calls.append(method)
            if method == "initialize":
                return 200, {"mcp-session-id": "session-123"}, {"result": {"protocolVersion": "2024-11-05"}}, "{}"
            if method == "tools/list":
                self.assertEqual(session_id, "session-123")
                return 200, {}, {"result": {"tools": [{"name": "list_pull_requests", "description": "List PRs"}]}}, "{}"
            raise AssertionError(f"Unexpected method: {method}")

        client = GitHubRemoteMcpClient(
            remote_url="https://example.com/mcp/",
            default_headers={"Authorization": "Bearer token"},
            post_jsonrpc=fake_post_jsonrpc,
        )

        tools = client.list_tools()

        self.assertEqual(calls, ["initialize", "tools/list"])
        self.assertEqual(tools[0]["name"], "list_pull_requests")

    def test_call_tool_initializes_session_first(self) -> None:
        calls: list[str] = []

        def fake_post_jsonrpc(remote_url, payload, *, default_headers, session_id=None, timeout=30):
            del remote_url, default_headers, timeout
            method = str(payload.get("method", ""))
            calls.append(method)
            if method == "initialize":
                return 200, {"mcp-session-id": "session-456"}, {"result": {"protocolVersion": "2024-11-05"}}, "{}"
            if method == "tools/call":
                self.assertEqual(session_id, "session-456")
                return 200, {}, {"result": {"content": [{"type": "text", "text": "ok"}], "isError": False}}, "{}"
            raise AssertionError(f"Unexpected method: {method}")

        client = GitHubRemoteMcpClient(
            remote_url="https://example.com/mcp/",
            default_headers={"Authorization": "Bearer token"},
            post_jsonrpc=fake_post_jsonrpc,
        )

        result = client.call_tool("list_pull_requests", {"owner": "truffle-ai"})

        self.assertEqual(calls, ["initialize", "tools/call"])
        self.assertEqual(result["content"][0]["text"], "ok")

class TestGitHubBackgroundWorker(unittest.TestCase):
    def test_verify_success(self) -> None:
        worker = GitHubBackgroundWorker()
        with patch.object(worker, "_load_access_token", return_value="gho_test"):
            with patch.object(worker, "_fetch_user_login", return_value="octocat"):
                ok, message = worker.verify()

        self.assertTrue(ok)
        self.assertIn("@octocat", message)

    def test_second_identical_cycle_is_suppressed(self) -> None:
        worker = GitHubBackgroundWorker()
        review_requested = SearchResult(total_count=1, items=[])
        authored_prs = SearchResult(total_count=0, items=[])
        involved_issues = SearchResult(total_count=0, items=[])
        org_activity = [OrgActivity(org="acme", issue_count=1, pr_count=0)]

        with patch.object(worker, "_load_access_token", return_value="gho_test"):
            with patch.object(worker, "_fetch_user_login", return_value="octocat"):
                with patch.object(worker, "_fetch_orgs", return_value=["acme"]):
                    with patch.object(
                        worker,
                        "_search",
                        side_effect=[review_requested, authored_prs, involved_issues] * 2,
                    ):
                        with patch.object(worker, "_fetch_org_activity", return_value=org_activity):
                            first = worker.run_cycle()
                            second = worker.run_cycle()

        self.assertTrue(first.changed)
        self.assertIsNotNone(first.summary)
        self.assertFalse(second.changed)
        self.assertIsNone(second.summary)
        self.assertEqual(second.uris, [])

    def test_auth_failure_returns_cycle_result(self) -> None:
        worker = GitHubBackgroundWorker()
        with patch.object(worker, "_load_access_token", side_effect=RuntimeError("GitHub OAuth token file not found")):
            result = worker.run_cycle()

        self.assertFalse(result.changed)
        self.assertIn("token file", result.error or result.auth_error or "")

    def test_fingerprint_prevents_resubmission(self) -> None:
        worker = GitHubBackgroundWorker()
        review = SearchResult(total_count=1, items=[])
        authored = SearchResult(total_count=0, items=[])
        issues = SearchResult(total_count=0, items=[])
        orgs: list[OrgActivity] = []

        fp1 = worker._make_fingerprint(
            login="octocat",
            review_requested=review,
            authored_prs=authored,
            involved_issues=issues,
            org_activity=orgs,
        )
        fp2 = worker._make_fingerprint(
            login="octocat",
            review_requested=review,
            authored_prs=authored,
            involved_issues=issues,
            org_activity=orgs,
        )
        self.assertEqual(fp1, fp2)

    def test_fingerprint_changes_on_new_activity(self) -> None:
        worker = GitHubBackgroundWorker()
        review_a = SearchResult(total_count=1, items=[])
        review_b = SearchResult(total_count=2, items=[])
        authored = SearchResult(total_count=0, items=[])
        issues = SearchResult(total_count=0, items=[])
        orgs: list[OrgActivity] = []

        fp_a = worker._make_fingerprint(
            login="octocat",
            review_requested=review_a,
            authored_prs=authored,
            involved_issues=issues,
            org_activity=orgs,
        )
        fp_b = worker._make_fingerprint(
            login="octocat",
            review_requested=review_b,
            authored_prs=authored,
            involved_issues=issues,
            org_activity=orgs,
        )
        self.assertNotEqual(fp_a, fp_b)

if __name__ == "__main__":
    unittest.main()
