"""Canonical foreground tool metadata for runtime registration and publishing."""

from __future__ import annotations

from dataclasses import dataclass


WHOOP_CONTEXT_NOTE = (
    "WHOOP strain is scored from 0-21; this app treats strain >=14 as high for alerts. "
    "Recovery is tied to the scored sleep/recovery period for a cycle, while an open cycle's "
    "strain is current-day load. Stick to WHOOP data and avoid medical claims."
)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    title: str
    description: str
    icon: str
    annotations: dict[str, bool]


READ_ONLY = {"readOnlyHint": True, "destructiveHint": False}


TOOLS = [
    ToolDefinition(
        name="whoop_status",
        title="WHOOP Status",
        description=(
            "Check WHOOP OAuth connectivity, installed token status, token expiry, and authenticated profile. "
            "Use this first for WHOOP auth smoke tests or connection troubleshooting."
        ),
        icon="heartbeat",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="get_profile_basic",
        title="Get Profile Basic",
        description=(
            "Fetch the authenticated WHOOP user's basic profile, including stable user identifiers and account "
            "metadata for context."
        ),
        icon="user-circle",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="get_body_measurements",
        title="Get Body Measurements",
        description=(
            "Fetch WHOOP body measurements and max heart rate for health-context summaries. Treat these as "
            "user-provided wearable data, not medical facts."
        ),
        icon="ruler",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="list_cycles",
        title="List Cycles",
        description=(
            "List recent WHOOP cycles with optional ISO timestamp start/end filters and next_token pagination for "
            f"recovery, strain, and readiness trend summaries. {WHOOP_CONTEXT_NOTE}"
        ),
        icon="repeat",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="get_cycle_by_id",
        title="Get Cycle By ID",
        description=(
            "Fetch one WHOOP cycle by numeric cycle_id for detailed strain, recovery linkage, and start/end timing "
            f"after list_cycles returns an id. {WHOOP_CONTEXT_NOTE}"
        ),
        icon="clock-counter-clockwise",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="list_recovery",
        title="List Recovery",
        description=(
            "List recent WHOOP recovery records with optional ISO timestamp start/end filters and next_token "
            f"pagination for readiness, HRV, resting heart rate, and recovery trend summaries. {WHOOP_CONTEXT_NOTE}"
        ),
        icon="battery-high",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="get_recovery_for_cycle",
        title="Get Recovery For Cycle",
        description=(
            f"Fetch the WHOOP recovery record associated with a numeric cycle_id after list_cycles returns a cycle. "
            f"{WHOOP_CONTEXT_NOTE}"
        ),
        icon="battery-charging",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="list_sleep",
        title="List Sleep",
        description=(
            "List recent WHOOP sleep records with optional ISO timestamp start/end filters and next_token pagination "
            "for sleep performance, efficiency, REM, SWS, awake time, and duration comparisons."
        ),
        icon="moon-stars",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="get_sleep_by_id",
        title="Get Sleep By ID",
        description=(
            "Fetch one WHOOP sleep record by sleep UUID after list_sleep returns an id, including sleep stages, "
            "timing, and score details."
        ),
        icon="bed",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="get_sleep_for_cycle",
        title="Get Sleep For Cycle",
        description=(
            "Fetch the WHOOP sleep record associated with a numeric cycle_id, including sleep stages, timing, and "
            "score details."
        ),
        icon="moon",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="list_workouts",
        title="List Workouts",
        description=(
            "List recent WHOOP workouts with optional ISO timestamp start/end filters and next_token pagination for "
            "strain, duration, heart rate, zones, and energy review. Use WHOOP strain, duration, heart rate, zones, "
            "and energy as data; avoid medical claims."
        ),
        icon="barbell",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="get_workout_by_id",
        title="Get Workout By ID",
        description=(
            "Fetch one WHOOP workout by workout UUID after list_workouts returns an id. Use WHOOP strain, duration, "
            "heart rate, zones, and energy as data; avoid medical claims."
        ),
        icon="person-simple-run",
        annotations=READ_ONLY,
    ),
    ToolDefinition(
        name="get_recent_whoop_summary",
        title="Get Recent WHOOP Summary",
        description=(
            "Fetch a compact WHOOP snapshot: profile, body measurements, latest cycle, latest recovery, latest "
            f"sleep, and recent workouts for health trend summaries and morning check-ins. {WHOOP_CONTEXT_NOTE}"
        ),
        icon="chart-line",
        annotations=READ_ONLY,
    ),
]


TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
