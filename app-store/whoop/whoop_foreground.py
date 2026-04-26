"""Foreground WHOOP app exposing read-only health data tools."""

from __future__ import annotations

import argparse
import atexit
import asyncio
import sys
from typing import Any

from truffile.app_runtime import ForegroundApp, ToolSpec, err, ok, phosphor_icon_url
from truffile.app_runtime.errors import AppAuthError

from whoop_client import WhoopApiError, WhoopClient


WHOOP_CONTEXT_NOTE = (
    "WHOOP strain is scored from 0-21; this app treats strain >=14 as high for alerts. "
    "Recovery is tied to the scored sleep/recovery period for a cycle, while an open cycle's "
    "strain is current-day load. Stick to WHOOP data and avoid medical claims."
)


def _validate_limit(limit: int) -> None:
    if limit < 1 or limit > 25:
        raise ValueError("limit must be between 1 and 25")


class WhoopForegroundApp(ForegroundApp):
    def __init__(self, *, client: WhoopClient | None = None) -> None:
        super().__init__("whoop", logger_name="whoop.foreground")
        self._client = client
        self._register_tools()

    def _get_client(self) -> WhoopClient:
        if self._client is None:
            self._client = WhoopClient()
        return self._client

    async def aclose(self) -> None:
        client = self._client
        if client is None:
            return
        self._client = None
        await client.close()

    async def _tool_error(self, exc: BaseException) -> dict[str, Any]:
        if isinstance(exc, AppAuthError):
            raise exc
        if isinstance(exc, WhoopApiError):
            return err(
                f"WHOOP API error: {exc.status_code}",
                kind="http",
                status_code=exc.status_code,
                response=exc.response_text[:1500],
            )
        return err(str(exc))

    @staticmethod
    def _list_result(label: str, payload: dict[str, Any]) -> dict[str, Any]:
        records = payload.get("records", [])
        count = len(records) if isinstance(records, list) else 0
        return ok(
            f"Fetched {count} {label}",
            records=records,
            count=count,
            next_token=payload.get("next_token"),
        )

    def _register_tools(self) -> None:
        @self.tool(
            ToolSpec(
                name="whoop_status",
                description="Verify WHOOP connectivity and show installed token status, including human-readable token expiry.",
                icon=phosphor_icon_url("heartbeat"),
                readonly=True,
            )
        )
        async def whoop_status() -> dict[str, Any]:
            try:
                client = self._get_client()
                ok_state, message = await client.verify()
                if not ok_state:
                    raise AppAuthError(message)
                profile = await client.get_profile_basic()
                return ok(message, auth=client.auth_status(), profile=profile)
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="get_profile_basic",
                description="Fetch the WHOOP user's basic profile.",
                icon=phosphor_icon_url("user-circle"),
                readonly=True,
            )
        )
        async def get_profile_basic() -> dict[str, Any]:
            try:
                return ok("WHOOP profile fetched", profile=await self._get_client().get_profile_basic())
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="get_body_measurements",
                description="Fetch the WHOOP user's body measurements and max heart rate.",
                icon=phosphor_icon_url("ruler"),
                readonly=True,
            )
        )
        async def get_body_measurements() -> dict[str, Any]:
            try:
                return ok(
                    "WHOOP body measurements fetched",
                    measurements=await self._get_client().get_body_measurements(),
                )
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="list_cycles",
                description=(
                    "List recent WHOOP cycles with optional time range filters. "
                    f"{WHOOP_CONTEXT_NOTE}"
                ),
                icon=phosphor_icon_url("repeat"),
                readonly=True,
            )
        )
        async def list_cycles(
            limit: int = 10,
            start: str | None = None,
            end: str | None = None,
            next_token: str | None = None,
        ) -> dict[str, Any]:
            try:
                _validate_limit(limit)
                payload = await self._get_client().list_cycles(
                    limit=limit,
                    start=start,
                    end=end,
                    next_token=next_token,
                )
                return self._list_result("cycles", payload)
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="get_cycle_by_id",
                description=(
                    "Fetch a single WHOOP cycle by numeric cycle id. "
                    f"{WHOOP_CONTEXT_NOTE}"
                ),
                icon=phosphor_icon_url("clock-counter-clockwise"),
                readonly=True,
            )
        )
        async def get_cycle_by_id(cycle_id: int) -> dict[str, Any]:
            try:
                return ok("WHOOP cycle fetched", cycle=await self._get_client().get_cycle_by_id(cycle_id))
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="list_recovery",
                description=(
                    "List recent WHOOP recovery records with optional time range filters. "
                    f"{WHOOP_CONTEXT_NOTE}"
                ),
                icon=phosphor_icon_url("battery-high"),
                readonly=True,
            )
        )
        async def list_recovery(
            limit: int = 10,
            start: str | None = None,
            end: str | None = None,
            next_token: str | None = None,
        ) -> dict[str, Any]:
            try:
                _validate_limit(limit)
                payload = await self._get_client().list_recovery(
                    limit=limit,
                    start=start,
                    end=end,
                    next_token=next_token,
                )
                return self._list_result("recovery records", payload)
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="get_recovery_for_cycle",
                description=(
                    "Fetch the WHOOP recovery record associated with a cycle id. "
                    f"{WHOOP_CONTEXT_NOTE}"
                ),
                icon=phosphor_icon_url("battery-charging"),
                readonly=True,
            )
        )
        async def get_recovery_for_cycle(cycle_id: int) -> dict[str, Any]:
            try:
                return ok(
                    "WHOOP recovery fetched",
                    recovery=await self._get_client().get_recovery_for_cycle(cycle_id),
                )
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="list_sleep",
                description=(
                    "List recent WHOOP sleep records with optional time range filters. "
                    "Use this for sleep performance, efficiency, REM, SWS, awake time, and sleep duration comparisons."
                ),
                icon=phosphor_icon_url("moon-stars"),
                readonly=True,
            )
        )
        async def list_sleep(
            limit: int = 10,
            start: str | None = None,
            end: str | None = None,
            next_token: str | None = None,
        ) -> dict[str, Any]:
            try:
                _validate_limit(limit)
                payload = await self._get_client().list_sleep(
                    limit=limit,
                    start=start,
                    end=end,
                    next_token=next_token,
                )
                return self._list_result("sleep records", payload)
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="get_sleep_by_id",
                description="Fetch a WHOOP sleep record by sleep UUID, including sleep stages and sleep score details.",
                icon=phosphor_icon_url("bed"),
                readonly=True,
            )
        )
        async def get_sleep_by_id(sleep_id: str) -> dict[str, Any]:
            try:
                return ok("WHOOP sleep fetched", sleep=await self._get_client().get_sleep_by_id(sleep_id))
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="get_sleep_for_cycle",
                description="Fetch the WHOOP sleep record associated with a cycle id, including sleep stages and sleep score details.",
                icon=phosphor_icon_url("moon"),
                readonly=True,
            )
        )
        async def get_sleep_for_cycle(cycle_id: int) -> dict[str, Any]:
            try:
                return ok("WHOOP cycle sleep fetched", sleep=await self._get_client().get_sleep_for_cycle(cycle_id))
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="list_workouts",
                description=(
                    "List recent WHOOP workouts with optional time range filters. "
                    "Use WHOOP strain, duration, heart rate, zones, and energy as data; avoid medical claims."
                ),
                icon=phosphor_icon_url("barbell"),
                readonly=True,
            )
        )
        async def list_workouts(
            limit: int = 10,
            start: str | None = None,
            end: str | None = None,
            next_token: str | None = None,
        ) -> dict[str, Any]:
            try:
                _validate_limit(limit)
                payload = await self._get_client().list_workouts(
                    limit=limit,
                    start=start,
                    end=end,
                    next_token=next_token,
                )
                return self._list_result("workouts", payload)
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="get_workout_by_id",
                description=(
                    "Fetch a WHOOP workout by workout UUID. "
                    "Use WHOOP strain, duration, heart rate, zones, and energy as data; avoid medical claims."
                ),
                icon=phosphor_icon_url("person-simple-run"),
                readonly=True,
            )
        )
        async def get_workout_by_id(workout_id: str) -> dict[str, Any]:
            try:
                return ok(
                    "WHOOP workout fetched",
                    workout=await self._get_client().get_workout_by_id(workout_id),
                )
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(
            ToolSpec(
                name="get_recent_whoop_summary",
                description=(
                    "Fetch a compact WHOOP snapshot: profile, body measurements, latest cycle, latest recovery, "
                    f"latest sleep, and recent workouts. {WHOOP_CONTEXT_NOTE}"
                ),
                icon=phosphor_icon_url("chart-line"),
                readonly=True,
            )
        )
        async def get_recent_whoop_summary() -> dict[str, Any]:
            try:
                return ok("WHOOP summary fetched", summary=await self._get_client().get_recent_summary())
            except Exception as exc:
                return await self._tool_error(exc)


app = WhoopForegroundApp()


def _cleanup() -> None:
    try:
        asyncio.run(app.aclose())
    except Exception:
        pass


atexit.register(_cleanup)


async def _verify_async() -> int:
    client = WhoopClient()
    try:
        ok_state, message = await client.verify()
    finally:
        await client.close()
    print(message, flush=True)
    return 0 if ok_state else 1


def verify() -> int:
    return asyncio.run(_verify_async())


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WHOOP foreground app")
    parser.add_argument("--verify", action="store_true", help="Verify the installed WHOOP OAuth credentials")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        if args.verify:
            return verify()
        app.run()
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
