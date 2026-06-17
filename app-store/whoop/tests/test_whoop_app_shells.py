from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from truffile.app_runtime.testing import AppHarness

_app_dir = Path(__file__).resolve().parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from truffile.app_runtime import AppAuthError
from bg_worker import BackgroundDigest, WhoopBackgroundWorker
from foreground import _TOOL_SPECS, WhoopForegroundApp
from tools import TOOLS_BY_NAME
from whoop_client import WhoopApiError
from whoop_background import WhoopBackgroundApp


def _mcp_text(result: object) -> str:
    content = getattr(result, "content")
    return str(content[0].text)


def _mcp_structured(result: object) -> dict[str, object]:
    structured = getattr(result, "structuredContent", None)
    return structured if isinstance(structured, dict) else {}


class _ForegroundClientStub:
    async def verify(self) -> tuple[bool, str]:
        return False, "WHOOP access token is missing"

    async def close(self) -> None:
        return None


class _SleepClientStub(_ForegroundClientStub):
    async def list_sleep(self, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "records": [
                {
                    "id": "sleep-1",
                    "start": "2026-04-26T08:04:19.830Z",
                    "end": "2026-04-26T16:28:18.140Z",
                    "timezone_offset": "-07:00",
                }
            ],
            "next_token": None,
        }


class _RawPayloadClientStub(_SleepClientStub):
    async def verify(self) -> tuple[bool, str]:
        return True, "WHOOP credentials verified"

    def auth_status(self) -> dict[str, object]:
        return {
            "client_id_configured": True,
            "has_access_token": True,
            "has_refresh_token": True,
        }

    async def get_profile_basic(self) -> dict[str, object]:
        return {"user_id": 123, "first_name": "Abdullah", "last_name": "Abdullah"}

    async def get_body_measurements(self) -> dict[str, object]:
        return {"height_cm": 180, "weight_kg": 80, "max_heart_rate": 188}

    async def get_cycle_by_id(self, cycle_id: int) -> dict[str, object]:
        raise WhoopApiError(
            "WHOOP API request failed for /v2/cycle/1",
            status_code=404,
            response_text="HTTP 404 Not Found",
        )

    async def get_recovery_for_cycle(self, cycle_id: int) -> dict[str, object]:
        raise WhoopApiError(
            "WHOOP API request failed for /v2/cycle/1/recovery",
            status_code=500,
            response_text="",
        )

    async def get_sleep_by_id(self, sleep_id: str) -> dict[str, object]:
        raise WhoopApiError(
            "WHOOP API request failed for /v2/activity/sleep/123",
            status_code=404,
            response_text="HTTP 404 Not Found",
        )

    async def get_sleep_for_cycle(self, cycle_id: int) -> dict[str, object]:
        raise WhoopApiError(
            "WHOOP API request failed for /v2/cycle/1/sleep",
            status_code=404,
            response_text="HTTP 404 Not Found",
        )

    async def get_recent_summary(self) -> dict[str, object]:
        return {
            "profile": await self.get_profile_basic(),
            "body_measurements": await self.get_body_measurements(),
            "recent_workouts": [],
            "recent_workouts_next_token": None,
        }


class _BgWhoopClientStub:
    def __init__(self) -> None:
        self.sleep_records = [
            {
                "id": "sleep-1",
                "start": "2026-06-10T07:00:00Z",
                "end": "2026-06-10T15:00:00Z",
                "updated_at": "2026-06-10T15:05:00Z",
                "score": {"sleep_performance_percentage": 87, "sleep_efficiency_percentage": 91},
            }
        ]
        self.workout_records = [
            {
                "id": "workout-1",
                "start": "2026-06-10T18:00:00Z",
                "end": "2026-06-10T18:45:00Z",
                "updated_at": "2026-06-10T19:00:00Z",
                "score": {"strain": 12.4, "average_heart_rate": 142},
                "sport_name": "Running",
            }
        ]
        self.recovery_records = [
            {
                "cycle_id": 10,
                "updated_at": "2026-06-10T16:00:00Z",
                "score": {"recovery_score": 72, "resting_heart_rate": 54, "hrv_rmssd_milli": 68},
            }
        ]
        self.cycle_records = [
            {
                "id": 10,
                "start": "2026-06-10T07:00:00Z",
                "end": "2026-06-11T07:00:00Z",
                "updated_at": "2026-06-11T07:10:00Z",
                "score": {"strain": 15.2},
            }
        ]

    async def close(self) -> None:
        return None

    async def verify(self) -> tuple[bool, str]:
        return True, "WHOOP auth OK"

    async def get_profile_basic(self) -> dict[str, object]:
        return {"user_id": 123, "first_name": "Abdullah", "last_name": "Abdullah"}

    async def get_body_measurements(self) -> dict[str, object]:
        return {"height_cm": 180, "weight_kg": 80, "max_heart_rate": 188}

    async def list_sleep(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return {"records": list(self.sleep_records), "next_token": None}

    async def list_workouts(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return {"records": list(self.workout_records), "next_token": None}

    async def list_recovery(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return {"records": list(self.recovery_records), "next_token": None}

    async def list_cycles(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return {"records": list(self.cycle_records), "next_token": None}


class TestWhoopAppShells(unittest.IsolatedAsyncioTestCase):
    async def test_user_info_resource_registered(self) -> None:
        app = WhoopForegroundApp(client=_RawPayloadClientStub())  # type: ignore[arg-type]
        uris = {entry["uri"] for entry in app.list_resources()}
        self.assertIn("truffle://user-info", uris)

    async def test_foreground_harness_runs_registered_read_tool(self) -> None:
        app = WhoopForegroundApp(client=_SleepClientStub())  # type: ignore[arg-type]
        harness = AppHarness(fg_app=app, logger_names=["whoop.foreground"])

        result = await harness.run_fg(calls=[("list_sleep", {"limit": 1})])

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        payload = result.tool_calls[0]["result"]
        text = _mcp_text(payload)
        structured = _mcp_structured(payload)
        self.assertIn("### WHOOP list_sleep", text)
        self.assertIn("Fetched 1 sleep records", text)
        self.assertFalse(text.lstrip().startswith("{"))
        self.assertEqual(structured["count"], 1)
        self.assertEqual(structured["query"]["limit"], 1)  # type: ignore[index]
        self.assertIn("start_utc", structured["records"][0])  # type: ignore[index]
        self.assertNotIn("status", structured)

    async def test_foreground_status_raises_auth_error_for_missing_token(self) -> None:
        app = WhoopForegroundApp(client=_ForegroundClientStub())  # type: ignore[arg-type]

        with patch.object(app._error_reporter, "report_foreground_exception", new=AsyncMock()):
            with self.assertRaisesRegex(AppAuthError, "WHOOP access token is missing"):
                await app.invoke_tool("whoop_status")

    async def test_foreground_bad_limit_returns_tool_error(self) -> None:
        app = WhoopForegroundApp(client=_ForegroundClientStub())  # type: ignore[arg-type]

        result = await app.invoke_tool("list_sleep", limit=0)

        self.assertTrue(result.isError)
        self.assertIn("limit must be between 1 and 25", _mcp_text(result))

    async def test_sleep_records_include_local_time_interpretation(self) -> None:
        app = WhoopForegroundApp(client=_SleepClientStub())  # type: ignore[arg-type]

        result = await app.invoke_tool("list_sleep", limit=1)
        structured = _mcp_structured(result)

        record = structured["records"][0]  # type: ignore[index]
        self.assertEqual(record["start"], "2026-04-26T08:04:19.830Z")
        self.assertEqual(record["start_utc"], "2026-04-26T08:04:19.830000Z")
        self.assertEqual(record["start_local"], "2026-04-26T01:04:19.830000-07:00")
        self.assertEqual(record["end_local"], "2026-04-26T09:28:18.140000-07:00")
        self.assertTrue(record["truffle_time_interpretation"]["raw_whoop_timestamps_with_z_are_utc"])
        self.assertEqual(structured["query"], {"limit": 1, "start": None, "end": None, "next_token": None})

    async def test_profile_tools_return_raw_schema_without_result_wrapper(self) -> None:
        app = WhoopForegroundApp(client=_RawPayloadClientStub())  # type: ignore[arg-type]

        cases = {
            "whoop_status": {"auth", "profile"},
            "get_profile_basic": {"profile"},
            "get_body_measurements": {"measurements"},
            "get_recent_whoop_summary": {"summary"},
        }
        for tool_name, expected_keys in cases.items():
            with self.subTest(tool_name=tool_name):
                result = await app.invoke_tool(tool_name)
                structured = _mcp_structured(result)

                self.assertFalse(result.isError)
                self.assertEqual(set(structured), expected_keys)
                self.assertNotIn("result", structured)
                self.assertNotIn("status", structured)
                self.assertNotIn("message", structured)

    async def test_http_errors_return_raw_error_schema_without_result_wrapper(self) -> None:
        app = WhoopForegroundApp(client=_RawPayloadClientStub())  # type: ignore[arg-type]

        cases = [
            ("get_cycle_by_id", {"cycle_id": 1}, 404, "HTTP 404 Not Found"),
            ("get_recovery_for_cycle", {"cycle_id": 1}, 500, ""),
            ("get_sleep_by_id", {"sleep_id": "123"}, 404, "HTTP 404 Not Found"),
            ("get_sleep_for_cycle", {"cycle_id": 1}, 404, "HTTP 404 Not Found"),
        ]
        for tool_name, kwargs, status_code, response in cases:
            with self.subTest(tool_name=tool_name):
                result = await app.invoke_tool(tool_name, **kwargs)
                structured = _mcp_structured(result)

                self.assertTrue(result.isError)
                self.assertEqual(
                    structured,
                    {"kind": "http", "status_code": status_code, "response": response},
                )
                self.assertNotIn("result", structured)
                self.assertNotIn("status", structured)
                self.assertNotIn("message", structured)


class TestWhoopBackground(unittest.IsolatedAsyncioTestCase):
    async def test_handle_cycle_result_submits_baseline_and_delta_digests(self) -> None:
        app = WhoopBackgroundApp()
        self.addCleanup(app.reset_for_test)
        harness = AppHarness(bg_app=app, logger_names=["whoop.background"])
        digests = [
            BackgroundDigest(
                generated_at="2026-06-11T00:00:00+00:00",
                seeded=True,
                baseline_digest="WHOOP baseline (2026-06-11): tracked 1 sleep record.",
            ),
            BackgroundDigest(
                generated_at="2026-06-11T12:00:00+00:00",
                delta_digest="WHOOP health digest (2026-06-11): 1 new or updated record.",
            ),
        ]

        def fake_run_cycle(worker):  # type: ignore[no-untyped-def]
            del worker
            return digests.pop(0)

        with patch.object(app, "run_cycle", side_effect=fake_run_cycle):
            result = await harness.run_bg(cycles=2)

        self.assertTrue(result.success)
        self.assertFalse(result.errors)
        self.assertEqual(len(result.submissions), 2)
        self.assertIn("WHOOP baseline", result.submissions[0]["text"])
        self.assertIn("WHOOP health digest", result.submissions[1]["text"])

    async def test_worker_baseline_then_only_changed_records(self) -> None:
        fake_client = _BgWhoopClientStub()
        worker = WhoopBackgroundWorker(client=fake_client)  # type: ignore[arg-type]
        self.addAsyncCleanup(worker.close)

        first = await worker.run_cycle()
        second = await worker.run_cycle()
        fake_client.sleep_records[0] = {
            **fake_client.sleep_records[0],
            "updated_at": "2026-06-11T15:05:00Z",
            "score": {"sleep_performance_percentage": 92, "sleep_efficiency_percentage": 94},
        }
        fake_client.workout_records.append(
            {
                "id": "workout-2",
                "start": "2026-06-11T18:00:00Z",
                "end": "2026-06-11T18:30:00Z",
                "updated_at": "2026-06-11T19:00:00Z",
                "score": {"strain": 8.1, "average_heart_rate": 132},
                "sport_name": "Cycling",
            }
        )
        third = await worker.run_cycle()

        self.assertTrue(first.seeded)
        self.assertIn("WHOOP baseline", first.baseline_digest)
        self.assertEqual(second.delta_digest, "")
        self.assertEqual(second.stats["changes"], 0)
        self.assertIn("WHOOP health digest", third.delta_digest)
        self.assertEqual(len(third.changes["sleep"]), 1)
        self.assertEqual(third.changes["sleep"][0]["_change_type"], "updated")
        self.assertEqual(len(third.changes["workouts"]), 1)
        self.assertEqual(third.changes["workouts"][0]["_change_type"], "new")


class TestWhoopToolMetadata(unittest.TestCase):
    def test_all_registered_tools_have_spec_entries(self) -> None:
        app = WhoopForegroundApp(client=_ForegroundClientStub())  # type: ignore[arg-type]
        registered_names = set(app._tools)
        spec_names = {spec.name for spec in _TOOL_SPECS}

        self.assertEqual(registered_names, spec_names)
        self.assertEqual(spec_names, set(TOOLS_BY_NAME))

    def test_all_tools_are_readonly_and_non_destructive(self) -> None:
        app = WhoopForegroundApp(client=_ForegroundClientStub())  # type: ignore[arg-type]

        for spec in _TOOL_SPECS:
            self.assertTrue(spec.annotations.get("readOnlyHint"), spec.name)
            self.assertFalse(spec.annotations.get("destructiveHint"), spec.name)
            registered_spec = app._tools[spec.name].spec
            if hasattr(registered_spec, "read_only"):
                self.assertTrue(registered_spec.read_only(), spec.name)
            elif hasattr(registered_spec, "readonly"):
                self.assertTrue(registered_spec.readonly, spec.name)

    def test_registered_tool_specs_have_titles_icons_and_descriptions(self) -> None:
        app = WhoopForegroundApp(client=_ForegroundClientStub())  # type: ignore[arg-type]

        for spec in _TOOL_SPECS:
            registered_spec = app._tools[spec.name].spec
            self.assertTrue(getattr(registered_spec, "description", ""), spec.name)
            self.assertTrue(getattr(registered_spec, "icon", ""), spec.name)
            if hasattr(registered_spec, "title"):
                self.assertEqual(registered_spec.title, spec.title)


if __name__ == "__main__":
    unittest.main()
