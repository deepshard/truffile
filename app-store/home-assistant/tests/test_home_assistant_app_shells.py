from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest.mock import AsyncMock

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(REPO_ROOT))

from truffile.app_runtime.testing import AppHarness

from home_assistant_foreground import HomeAssistantForegroundApp


class TestHomeAssistantAppShells(unittest.IsolatedAsyncioTestCase):
    async def test_foreground_harness_runs_readonly_tool(self) -> None:
        fake_client = AsyncMock()
        fake_client.call_tool.return_value = {
            "content": [{"type": "text", "text": "Kitchen light is on."}],
            "isError": False,
        }
        app = HomeAssistantForegroundApp(client=fake_client)
        harness = AppHarness(fg_app=app, logger_names=["home_assistant.foreground"])

        result = await harness.run_fg(
            calls=[
                (
                    "ha_get_live_context",
                    {
                        "entity_name": "kitchen light",
                        "area": None,
                        "domain": "light",
                    },
                )
            ]
        )

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        self.assertEqual(result.tool_calls[0]["tool"], "ha_get_live_context")
        self.assertIn("Kitchen", result.tool_calls[0]["result"]["content"][0]["text"])
        fake_client.call_tool.assert_awaited_once_with(
            "GetLiveContext",
            {
                "name": "kitchen light",
                "domain": "light",
            },
        )

    async def test_foreground_blocks_safety_sensitive_action_before_remote_call(self) -> None:
        fake_client = AsyncMock()
        app = HomeAssistantForegroundApp(client=fake_client)
        harness = AppHarness(fg_app=app, logger_names=["home_assistant.foreground"])

        result = await harness.run_fg(
            calls=[
                (
                    "ha_turn_on",
                    {
                        "entity_name": "front door lock",
                        "area": None,
                        "domain": "lock",
                    },
                )
            ]
        )

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        tool_result = result.tool_calls[0]["result"]
        self.assertEqual(tool_result["status"], "error")
        self.assertTrue(tool_result["requires_confirmation"])
        fake_client.call_tool.assert_not_called()

    async def test_foreground_lists_capabilities(self) -> None:
        fake_client = AsyncMock()
        fake_client.list_tools.return_value = [{"name": "GetLiveContext"}]
        fake_client.list_resources.return_value = [{"uri": "homeassistant://assist/context-snapshot"}]
        fake_client.list_prompts.return_value = []
        app = HomeAssistantForegroundApp(client=fake_client)
        harness = AppHarness(fg_app=app, logger_names=["home_assistant.foreground"])

        result = await harness.run_fg(calls=[("ha_list_capabilities", {})])

        self.assertTrue(result.success)
        self.assertEqual(result.tool_calls[0]["result"]["status"], "success")
        self.assertIn("ha_get_live_context", {tool["name"] for tool in app.list_tools()})
        self.assertEqual(app.list_prompts(), [])


if __name__ == "__main__":
    unittest.main()
