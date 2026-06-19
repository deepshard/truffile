"""Foreground WHOOP app exposing read-only health data tools."""

from __future__ import annotations

import argparse
import atexit
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import functools
import inspect
import os
import sys
from typing import Any, Callable

from mcp.types import CallToolResult, TextContent
from truffile.app_runtime import ForegroundApp, ToolSpec, err, ok, phosphor_icon_url
from truffile.app_runtime.errors import AppAuthError

from tools import TOOLS as _TOOL_SPECS, TOOLS_BY_NAME, ToolDefinition
from whoop_client import WhoopApiError, WhoopClient


_TOOLSPEC_PARAMETERS = set(inspect.signature(ToolSpec).parameters)


def _validate_limit(limit: int) -> None:
    if limit < 1 or limit > 25:
        raise ValueError("limit must be between 1 and 25")


def _parse_timezone_offset(offset: str) -> timezone | None:
    value = str(offset or "").strip()
    if not value or value == "Z":
        return timezone.utc
    sign = 1
    if value.startswith("-"):
        sign = -1
        value = value[1:]
    elif value.startswith("+"):
        value = value[1:]
    try:
        hours_raw, minutes_raw = value.split(":", 1)
        delta = timedelta(hours=int(hours_raw), minutes=int(minutes_raw))
        return timezone(sign * delta)
    except Exception:
        return None


def _parse_utc_timestamp(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _annotate_whoop_time_fields(record: dict[str, Any]) -> dict[str, Any]:
    annotated = deepcopy(record)
    offset = str(annotated.get("timezone_offset", "") or "").strip()
    tz = _parse_timezone_offset(offset)
    if tz is None:
        return annotated

    interpretations: dict[str, dict[str, str]] = {}
    for field in ("start", "end", "created_at", "updated_at"):
        utc_dt = _parse_utc_timestamp(str(annotated.get(field, "") or ""))
        if utc_dt is None:
            continue
        local_dt = utc_dt.astimezone(tz)
        annotated[f"{field}_utc"] = utc_dt.isoformat().replace("+00:00", "Z")
        annotated[f"{field}_local"] = local_dt.isoformat()
        interpretations[field] = {
            "raw": str(annotated.get(field, "") or ""),
            "utc": annotated[f"{field}_utc"],
            "local": annotated[f"{field}_local"],
            "timezone_offset": offset,
        }

    if interpretations:
        annotated["truffle_time_interpretation"] = {
            "raw_whoop_timestamps_with_z_are_utc": True,
            "timezone_offset_source": "WHOOP timezone_offset",
            "note": "Convert UTC timestamps by applying timezone_offset. Example: 08:04Z with -07:00 is 01:04 local time.",
            "fields": interpretations,
        }
    return annotated


def _annotate_whoop_payload_times(payload: Any) -> Any:
    if isinstance(payload, dict):
        if any(key in payload for key in ("start", "end")) and "timezone_offset" in payload:
            return _annotate_whoop_time_fields(payload)
        return {key: _annotate_whoop_payload_times(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_annotate_whoop_payload_times(item) for item in payload]
    return payload


def _text_result(
    text: str,
    *,
    structured: dict[str, Any] | None = None,
    is_error: bool = False,
) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text.strip() or "WHOOP returned no visible details.")],
        structuredContent=structured or None,
        isError=is_error,
    )


def _compact_scalar(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return None


def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _score_value(record: dict[str, Any], key: str) -> Any:
    score = record.get("score")
    if isinstance(score, dict):
        value = score.get(key)
        if value not in (None, "", [], {}):
            return value
    return record.get(key)


def _dict_bits(data: dict[str, Any], keys: tuple[str, ...], *, prefix: str = "") -> list[str]:
    bits: list[str] = []
    for key in keys:
        value = data.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list)):
            continue
        bits.append(f"{prefix}{key}={value}")
    return bits


def _record_row(record: dict[str, Any]) -> str:
    label = _first_present(record, ("id", "cycle_id", "sleep_id", "workout_id", "user_id")) or "record"
    bits: list[str] = []
    bits.extend(_dict_bits(record, ("start_local", "end_local", "start_utc", "end_utc", "timezone_offset")))
    for key in (
        "strain",
        "average_heart_rate",
        "max_heart_rate",
        "kilojoule",
        "recovery_score",
        "resting_heart_rate",
        "hrv_rmssd_milli",
        "sleep_performance_percentage",
        "sleep_efficiency_percentage",
        "respiratory_rate",
    ):
        value = _score_value(record, key)
        if value not in (None, "", [], {}):
            bits.append(f"{key}={value}")
    bits.extend(_dict_bits(record, ("sport_id", "sport_name", "nap", "complete", "is_nap")))
    return f"- {label}" + (f" ({'; '.join(bits[:10])})" if bits else "")


def _append_rows(lines: list[str], title: str, records: Any, *, max_rows: int = 8) -> None:
    if not isinstance(records, list):
        return
    if not records:
        lines.append(f"{title}: none")
        return
    lines.append(f"{title}:")
    for record in records[:max_rows]:
        if isinstance(record, dict):
            lines.append(_record_row(record))
        else:
            lines.append(f"- {record}")
    if len(records) > max_rows:
        lines.append(f"- ... {len(records) - max_rows} more")


def _append_dict_summary(lines: list[str], title: str, data: Any) -> None:
    if not isinstance(data, dict):
        return
    bits = _dict_bits(
        data,
        (
            "user_id",
            "email",
            "first_name",
            "last_name",
            "height_meter",
            "weight_kilogram",
            "max_heart_rate",
            "cycle_id",
            "sleep_id",
            "workout_id",
            "start_local",
            "end_local",
            "start_utc",
            "end_utc",
            "timezone_offset",
            "expires_at",
            "has_access_token",
            "has_refresh_token",
        ),
    )
    for key in (
        "strain",
        "recovery_score",
        "sleep_performance_percentage",
        "average_heart_rate",
        "max_heart_rate",
        "resting_heart_rate",
        "hrv_rmssd_milli",
    ):
        value = _score_value(data, key)
        if value not in (None, "", [], {}):
            bits.append(f"{key}={value}")
    if bits:
        lines.append(f"{title}: " + ", ".join(bits[:14]))


def _append_summary(lines: list[str], summary: Any) -> None:
    if not isinstance(summary, dict):
        return
    _append_dict_summary(lines, "Profile", summary.get("profile"))
    _append_dict_summary(lines, "Body", summary.get("body_measurements"))
    _append_dict_summary(lines, "Latest cycle", summary.get("latest_cycle"))
    _append_dict_summary(lines, "Latest recovery", summary.get("latest_recovery"))
    _append_dict_summary(lines, "Latest sleep", summary.get("latest_sleep"))
    _append_rows(lines, "Recent workouts", summary.get("recent_workouts"), max_rows=3)
    next_token = summary.get("recent_workouts_next_token")
    if next_token:
        lines.append(f"recent_workouts_next_token={next_token}")


def _format_whoop_text(tool_name: str, payload: dict[str, Any], structured: dict[str, Any]) -> str:
    lines = [f"### WHOOP {tool_name}"]
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        lines.append(message.strip())

    _append_rows(lines, "Records", structured.get("records"))
    for key, title in (
        ("profile", "Profile"),
        ("measurements", "Measurements"),
        ("cycle", "Cycle"),
        ("recovery", "Recovery"),
        ("sleep", "Sleep"),
        ("workout", "Workout"),
        ("auth", "Auth"),
    ):
        _append_dict_summary(lines, title, structured.get(key))
    _append_summary(lines, structured.get("summary"))

    details: list[str] = []
    for key in ("count", "next_token", "cycle_id", "sleep_id", "workout_id", "kind", "status_code"):
        value = _compact_scalar(structured.get(key))
        if value is not None:
            details.append(f"{key}={value}")
    query = structured.get("query")
    if isinstance(query, dict):
        query_bits = _dict_bits(query, tuple(query.keys()))
        if query_bits:
            details.append("query: " + ", ".join(query_bits))
    if details:
        lines.append("Details: " + "; ".join(details))

    return "\n".join(line for line in lines if line)


def _format_whoop_result(tool_name: str, payload: Any) -> CallToolResult:
    if isinstance(payload, CallToolResult):
        return payload
    if not isinstance(payload, dict):
        return _text_result(f"### WHOOP {tool_name}\n{payload}")
    structured = {key: value for key, value in payload.items() if key not in {"status", "message"}}
    is_error = payload.get("status") == "error" or (
        payload.get("kind") == "http" and int(payload.get("status_code") or 0) >= 400
    )
    return _text_result(
        _format_whoop_text(tool_name, payload, structured),
        structured=structured,
        is_error=is_error,
    )


def _make_tool_spec(*, name: str) -> ToolSpec:
    entry: ToolDefinition = TOOLS_BY_NAME[name]
    kwargs: dict[str, Any] = {
        "name": entry.name,
        "description": entry.description,
        "icon": phosphor_icon_url(entry.icon),
    }
    if "title" in _TOOLSPEC_PARAMETERS:
        kwargs["title"] = entry.title
    if "annotations" in _TOOLSPEC_PARAMETERS:
        kwargs["annotations"] = dict(entry.annotations)
    if "readonly" in _TOOLSPEC_PARAMETERS:
        kwargs["readonly"] = bool(entry.annotations.get("readOnlyHint"))
    if "read_only" in _TOOLSPEC_PARAMETERS:
        kwargs["read_only"] = bool(entry.annotations.get("readOnlyHint"))
    if "destructive" in _TOOLSPEC_PARAMETERS:
        kwargs["destructive"] = bool(entry.annotations.get("destructiveHint"))
    if "structured_output" in _TOOLSPEC_PARAMETERS:
        kwargs["structured_output"] = False
    return ToolSpec(**kwargs)


class WhoopForegroundApp(ForegroundApp):
    def __init__(self, *, client: WhoopClient | None = None) -> None:
        super().__init__("whoop", logger_name="whoop.foreground")
        self._client = client
        self._register_tools()
        self._register_user_info_resource()

    def _get_client(self) -> WhoopClient:
        if self._client is None:
            self._client = WhoopClient()
        return self._client

    def _register_user_info_resource(self) -> None:
        @self.user_info_resource()
        async def whoop_user_info() -> str:
            lines = ["# WHOOP"]
            try:
                profile = await self._get_client().get_profile_basic()
            except Exception:
                profile = {}
            first = str(profile.get("first_name") or "").strip()
            last = str(profile.get("last_name") or "").strip()
            name = " ".join(part for part in (first, last) if part).strip()
            email = str(profile.get("email") or "").strip()
            if name or email:
                account = name or "WHOOP user"
                if email:
                    account = f"{account} ({email})"
                lines.append(f"Account: {account}")
            else:
                lines.append("Account: WHOOP OAuth connected")
            if profile.get("user_id"):
                lines.append(f"User ID: {profile['user_id']}")
            lines.append("Health context: recovery, sleep, cycle, workout, and body-measurement tools are connected.")
            lines.append("More: use whoop_recent_summary / get_profile_basic / list_recovery / list_sleep.")
            return "\n".join(lines)

    async def aclose(self) -> None:
        client = self._client
        if client is None:
            return
        self._client = None
        await client.close()

    def _wrap_tool(self, tool_name: str, func: Callable[..., Any]) -> Callable[..., Any]:
        wrapped = super()._wrap_tool(tool_name, func)

        @functools.wraps(func)
        async def formatted(*args: Any, **kwargs: Any) -> CallToolResult:
            return _format_whoop_result(tool_name, await wrapped(*args, **kwargs))

        formatted.__signature__ = inspect.signature(func).replace(return_annotation=Any)  # type: ignore[attr-defined]
        return formatted

    async def _tool_error(self, exc: BaseException) -> dict[str, Any]:
        if isinstance(exc, AppAuthError):
            raise exc
        if isinstance(exc, WhoopApiError):
            return {
                "kind": "http",
                "status_code": exc.status_code,
                "response": exc.response_text[:1500],
            }
        return err(str(exc))

    @staticmethod
    def _list_result(label: str, payload: dict[str, Any], *, query: dict[str, Any]) -> dict[str, Any]:
        records = payload.get("records", [])
        annotated_records = _annotate_whoop_payload_times(records)
        count = len(records) if isinstance(records, list) else 0
        return ok(
            f"Fetched {count} {label}",
            records=annotated_records,
            count=count,
            next_token=payload.get("next_token"),
            query=query,
        )

    def _register_tools(self) -> None:
        @self.tool(_make_tool_spec(name="whoop_status"))
        async def whoop_status() -> dict[str, Any]:
            try:
                client = self._get_client()
                ok_state, message = await client.verify()
                if not ok_state:
                    raise AppAuthError(message)
                profile = await client.get_profile_basic()
                return {"auth": client.auth_status(), "profile": profile}
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="get_profile_basic"))
        async def get_profile_basic() -> dict[str, Any]:
            try:
                return {"profile": await self._get_client().get_profile_basic()}
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="get_body_measurements"))
        async def get_body_measurements() -> dict[str, Any]:
            try:
                return {"measurements": await self._get_client().get_body_measurements()}
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="list_cycles"))
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
                return self._list_result(
                    "cycles",
                    payload,
                    query={"limit": limit, "start": start, "end": end, "next_token": next_token},
                )
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="get_cycle_by_id"))
        async def get_cycle_by_id(cycle_id: int) -> dict[str, Any]:
            try:
                return {
                    "cycle": _annotate_whoop_payload_times(await self._get_client().get_cycle_by_id(cycle_id)),
                    "cycle_id": cycle_id,
                }
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="list_recovery"))
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
                return self._list_result(
                    "recovery records",
                    payload,
                    query={"limit": limit, "start": start, "end": end, "next_token": next_token},
                )
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="get_recovery_for_cycle"))
        async def get_recovery_for_cycle(cycle_id: int) -> dict[str, Any]:
            try:
                return {
                    "recovery": _annotate_whoop_payload_times(await self._get_client().get_recovery_for_cycle(cycle_id)),
                    "cycle_id": cycle_id,
                }
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="list_sleep"))
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
                return self._list_result(
                    "sleep records",
                    payload,
                    query={"limit": limit, "start": start, "end": end, "next_token": next_token},
                )
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="get_sleep_by_id"))
        async def get_sleep_by_id(sleep_id: str) -> dict[str, Any]:
            try:
                return {
                    "sleep": _annotate_whoop_payload_times(await self._get_client().get_sleep_by_id(sleep_id)),
                    "sleep_id": sleep_id,
                }
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="get_sleep_for_cycle"))
        async def get_sleep_for_cycle(cycle_id: int) -> dict[str, Any]:
            try:
                return {
                    "sleep": _annotate_whoop_payload_times(await self._get_client().get_sleep_for_cycle(cycle_id)),
                    "cycle_id": cycle_id,
                }
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="list_workouts"))
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
                return self._list_result(
                    "workouts",
                    payload,
                    query={"limit": limit, "start": start, "end": end, "next_token": next_token},
                )
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="get_workout_by_id"))
        async def get_workout_by_id(workout_id: str) -> dict[str, Any]:
            try:
                return ok(
                    "WHOOP workout fetched",
                    workout=_annotate_whoop_payload_times(await self._get_client().get_workout_by_id(workout_id)),
                    workout_id=workout_id,
                )
            except Exception as exc:
                return await self._tool_error(exc)

        @self.tool(_make_tool_spec(name="get_recent_whoop_summary"))
        async def get_recent_whoop_summary() -> dict[str, Any]:
            try:
                return {"summary": _annotate_whoop_payload_times(await self._get_client().get_recent_summary())}
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
    if str(os.getenv("APP_STORE_USE_TEST_STUBS", "")).strip() == "1":
        print("WHOOP probe stubs enabled; skipping OAuth verification", flush=True)
        return 0
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
