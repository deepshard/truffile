from __future__ import annotations

import unittest
from unittest.mock import patch

from truffile.app_runtime.testing import AppHarness
from background import app as viator_bg_app
from foreground import ViatorForegroundApp


class _FakeRemoteClient:
    def list_tools(self) -> list[dict[str, object]]:
        return [
            {
                "name": "search_experiences",
                "description": "Search Viator experiences.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "searchTerm": {"type": "string"},
                        "startDate": {"type": "string"},
                        "endDate": {"type": "string"},
                        "sessionId": {"type": "string"},
                    },
                    "required": ["startDate", "endDate", "sessionId"],
                },
            },
            {
                "name": "get_experience_details",
                "description": "Get Viator experience details.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "sessionId": {"type": "string"},
                    },
                    "required": ["code", "sessionId"],
                },
            },
        ]

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {
            "content": [{"type": "text", "text": f"stub:{name}"}],
            "structuredContent": {"name": name, "arguments": arguments},
            "isError": False,
        }


class TestViatorAppShells(unittest.IsolatedAsyncioTestCase):
    async def test_foreground_harness_runs_registered_tool(self) -> None:
        app = ViatorForegroundApp(client=_FakeRemoteClient())
        harness = AppHarness(fg_app=app, logger_names=["viator.foreground"])

        result = await harness.run_fg(
            calls=[
                (
                    "search_experiences",
                    {
                        "searchTerm": "walking tours in Paris",
                        "startDate": "2026-05-02",
                        "endDate": "2026-05-03",
                        "sessionId": "session_example",
                    },
                )
            ]
        )

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        self.assertEqual(result.tool_calls[0]["tool"], "search_experiences")
        self.assertEqual(result.tool_calls[0]["result"]["structuredContent"]["name"], "search_experiences")
        self.assertIn("get_experience_details", {tool["name"] for tool in app.list_tools()})
        self.assertEqual(app.list_prompts(), [])

    async def test_foreground_harness_surfaces_remote_errors(self) -> None:
        class ExplodingClient(_FakeRemoteClient):
            def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
                del name, arguments
                raise RuntimeError("remote explode")

        app = ViatorForegroundApp(client=ExplodingClient())
        harness = AppHarness(fg_app=app, logger_names=["viator.foreground"])

        result = await harness.run_fg(calls=[("get_experience_details", {"code": "8954P40", "sessionId": "session_example"})])

        self.assertFalse(result.success)
        self.assertTrue(result.errors)
        self.assertIn("remote explode", result.errors[0])

    async def test_background_uses_cached_location_then_suppresses_repeat(self) -> None:
        location_json = (
            '{"city":"Los Angeles","regionName":"California","country":"United States",'
            '"zip":"90034","lat":34.029,"lon":-118.4005,"timezone":"America/Los_Angeles"}'
        )
        viator_bg_app.reset_for_test()
        harness = AppHarness(bg_app=viator_bg_app, logger_names=["viator.background"])
        with patch.dict(
            "os.environ",
            {
                "TRUFFLE_USER_LOCATION_JSON": location_json,
                "VIATOR_BG_FETCH_IP_LOCATION": "0",
                "VIATOR_BG_LOCATION_HINT_HOURS": "48",
            },
        ):
            result = await harness.run_bg(cycles=2)

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        self.assertEqual(len(result.submissions), 1)
        text = result.submissions[0]["text"]
        self.assertIn("Viator local travel context", text)
        self.assertIn("Los Angeles, California, United States", text)
        self.assertIn('searchTerm="things to do near Los Angeles, California"', text)
        self.assertIn("cadence=48h", text)
        self.assertIn("Actions you can do with this", text)


if __name__ == "__main__":
    unittest.main()
