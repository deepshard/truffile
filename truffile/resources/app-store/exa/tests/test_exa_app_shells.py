from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

from truffile.app_runtime.testing import AppHarness
from exa_foreground import ExaForegroundApp

class TestExaAppShells(unittest.IsolatedAsyncioTestCase):
    async def test_foreground_harness_runs_registered_tool(self) -> None:
        fake_client = AsyncMock()
        fake_client.call_tool.return_value = {
            "content": [{"type": "text", "text": "OpenAI released a new post today."}],
            "isError": False,
        }
        app = ExaForegroundApp(client=fake_client)
        harness = AppHarness(
            fg_app=app,
            logger_names=["exa.foreground"],
        )

        result = await harness.run_fg(
            calls=[
                (
                    "web_search_exa",
                    {
                        "query": "latest OpenAI news",
                        "num_results": 3,
                        "include_text": False,
                    },
                )
            ]
        )

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        self.assertEqual(result.tool_calls[0]["tool"], "web_search_exa")
        self.assertIn("OpenAI", result.tool_calls[0]["result"]["content"][0]["text"])
        fake_client.call_tool.assert_awaited_once_with(
            "web_search_exa",
            {
                "query": "latest OpenAI news",
                "num_results": 3,
                "include_text": False,
            },
        )
        self.assertIn("web_search_exa", {tool["name"] for tool in app.list_tools()})
        self.assertEqual(app.list_prompts(), [])

    async def test_foreground_harness_surfaces_remote_errors(self) -> None:
        fake_client = AsyncMock()
        fake_client.call_tool.side_effect = RuntimeError("remote explode")
        app = ExaForegroundApp(client=fake_client)
        harness = AppHarness(
            fg_app=app,
            logger_names=["exa.foreground"],
        )

        result = await harness.run_fg(
            calls=[
                (
                    "company_research_exa",
                    {
                        "query": "Anthropic",
                    },
                )
            ]
        )

        self.assertFalse(result.success)
        self.assertTrue(result.errors)
        self.assertIn("remote explode", result.errors[0])

if __name__ == "__main__":
    unittest.main()
