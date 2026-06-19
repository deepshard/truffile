from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from truffile.app_runtime.testing import AppHarness
from notion_foreground import app as notion_fg_app, reset_for_test, set_auth_for_test, set_client

class _FakeNotionClient:
    def verify(self) -> tuple[bool, str]:
        return True, "Notion MCP verified. tools=3"

    def list_tools(self) -> list[dict[str, object]]:
        return [
            {
                "name": "notion_fetch",
                "description": "Fetch a Notion page or database.",
                "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
            },
            {
                "name": "notion_search",
                "description": "Search the Notion workspace.",
                "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {
            "content": [{"type": "text", "text": f"stub:{name}"}],
            "structuredContent": {"name": name, "arguments": arguments},
            "isError": False,
        }

    def close(self) -> None:
        return None

class _FakeNotionAuth:
    def __init__(self, token: str = "ntn_shared_token") -> None:
        self.token = token
        self.calls = 0

    def get_access_token(self) -> str:
        self.calls += 1
        return self.token

class TestNotionAppShells(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reset_for_test()

    async def test_foreground_harness_runs_registered_tool(self) -> None:
        set_client(_FakeNotionClient())
        harness = AppHarness(
            fg_app=notion_fg_app,
            logger_names=["notion.foreground"],
        )
        result = await harness.run_fg(
            calls=[
                ("notion_search", {"query": "meeting notes"}),
                ("notion_fetch", {"id": "page-123"}),
            ]
        )

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        self.assertEqual(result.tool_calls[0]["result"]["structuredContent"]["name"], "notion_search")
        self.assertEqual(result.tool_calls[1]["result"]["structuredContent"]["arguments"]["id"], "page-123")
        tool_names = {tool["name"] for tool in notion_fg_app.list_tools()}
        self.assertIn("notion_search", tool_names)
        self.assertIn("notion_fetch", tool_names)

    async def test_verify_uses_env_access_token(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "NOTION_ACCESS_TOKEN": "ntn_test_token",
                "APP_STORE_USE_TEST_STUBS": "1",
            },
            clear=False,
        ), patch(
            "notion_foreground.verify_notion_workspace",
            return_value=(True, "workspace=Testing"),
        ):
            ok, message = notion_fg_app.verify()

        self.assertTrue(ok)
        self.assertIn("workspace=Testing", message)

    async def test_build_client_uses_shared_auth_manager(self) -> None:
        fake_auth = _FakeNotionAuth("ntn_shared_auth")
        set_auth_for_test(fake_auth)
        with patch("notion_foreground.resolve_binary", return_value="/usr/local/bin/notion-mcp-server"), \
             patch("notion_foreground.ManagedNotionMcpProcessClient") as managed_client:
            notion_fg_app.build_client()

        self.assertEqual(fake_auth.calls, 1)
        managed_client.assert_called_once_with(
            notion_token="ntn_shared_auth",
            server_bin="/usr/local/bin/notion-mcp-server",
        )

    async def test_reset_for_test_closes_cached_client(self) -> None:
        client = MagicMock(spec=_FakeNotionClient)
        set_client(client)

        reset_for_test()

        client.close.assert_called_once_with()

    async def test_verify_uses_shared_auth_manager(self) -> None:
        fake_auth = _FakeNotionAuth("ntn_shared_verify")
        set_auth_for_test(fake_auth)
        with patch("notion_foreground.verify_notion_workspace", return_value=(True, "workspace=Testing")), \
             patch("notion_foreground.resolve_binary", return_value="/usr/local/bin/notion-mcp-server"), \
             patch("notion_foreground.ManagedNotionMcpProcessClient") as managed_client:
            managed_instance = managed_client.return_value
            managed_instance.verify.return_value = (True, "Notion MCP verified. tools=3")

            ok, message = notion_fg_app.verify()

        self.assertTrue(ok)
        self.assertIn("workspace=Testing", message)
        self.assertEqual(fake_auth.calls, 2)
        managed_client.assert_called_once_with(
            notion_token="ntn_shared_verify",
            server_bin="/usr/local/bin/notion-mcp-server",
        )
        managed_instance.close.assert_called_once_with()

if __name__ == "__main__":
    unittest.main()
