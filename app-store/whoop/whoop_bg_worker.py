# Draft background worker. It is intentionally not enabled in truffile.yaml
# for the foreground-only PR.
"""Background WHOOP worker that prepares ambient health signals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from truffile.app_runtime import AppAuthError
from truffle.app.background_pb2 import BackgroundContext

from whoop_client import WhoopApiError, WhoopClient

LOW_RECOVERY_THRESHOLD = 34.0
LOW_SLEEP_PERFORMANCE_THRESHOLD = 70.0
HIGH_STRAIN_THRESHOLD = 14.0
SHORT_SLEEP_MILLI = 6 * 60 * 60 * 1000

_PRIORITY_LOW = getattr(BackgroundContext, "PRIORITY_LOW", getattr(BackgroundContext, "PRIORITY_DEFAULT", 0))
_PRIORITY_DEFAULT = getattr(BackgroundContext, "PRIORITY_DEFAULT", getattr(BackgroundContext, "PRIORITY_HIGH", 1))
_PRIORITY_HIGH = getattr(BackgroundContext, "PRIORITY_HIGH", _PRIORITY_DEFAULT)


@dataclass(frozen=True, slots=True)
class PreparedSubmission:
    text: str
    uris: tuple[str, ...] = ()
    priority: int = _PRIORITY_DEFAULT


@dataclass(frozen=True, slots=True)
class BgRunResult:
    submissions: list[PreparedSubmission] = field(default_factory=list)
    auth_error: str | None = None
    error: str | None = None


class WhoopBackgroundWorker:
    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client or WhoopClient()
        self._seeded = False
        self._seen_fingerprints: set[str] = set()
        self._last_mismatch_key: str | None = None

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            await close()

    async def verify(self) -> tuple[bool, str]:
        try:
            return await self._client.verify()
        except Exception as exc:
            return False, f"WHOOP background verification failed: {exc}"

    async def run_cycle(self) -> BgRunResult:
        try:
            summary = await self._client.get_recent_summary()
        except AppAuthError as exc:
            return BgRunResult(auth_error=str(exc))
        except WhoopApiError as exc:
            if exc.status_code in {401, 403}:
                return BgRunResult(auth_error=str(exc))
            return BgRunResult(error=f"WHOOP API error: HTTP {exc.status_code}")
        except Exception as exc:
            return BgRunResult(error=str(exc))

        if not self._seeded:
            self._seed(summary)
            self._seeded = True
            snapshot = self._build_snapshot(summary)
            if not snapshot:
                return BgRunResult()
            return BgRunResult(submissions=[PreparedSubmission(text=snapshot, priority=_PRIORITY_LOW)])

        submissions = self._build_changed_submissions(summary)
        return BgRunResult(submissions=submissions)

    def _seed(self, summary: dict[str, Any]) -> None:
        for kind, item in self._iter_items(summary):
            fp = self._fingerprint(kind, item)
            if fp:
                self._seen_fingerprints.add(fp)

        recovery = self._dict_or_none(summary.get("latest_recovery"))
        cycle = self._dict_or_none(summary.get("latest_cycle"))
        self._last_mismatch_key = self._mismatch_key(recovery, cycle)

    def _build_changed_submissions(self, summary: dict[str, Any]) -> list[PreparedSubmission]:
        submissions: list[PreparedSubmission] = []
        for kind, item in self._iter_items(summary):
            fp = self._fingerprint(kind, item)
            if not fp or fp in self._seen_fingerprints:
                continue
            self._seen_fingerprints.add(fp)
            submission = self._submission_for(kind, item)
            if submission is not None:
                submissions.append(submission)

        recovery = self._dict_or_none(summary.get("latest_recovery"))
        cycle = self._dict_or_none(summary.get("latest_cycle"))
        mismatch_key = self._mismatch_key(recovery, cycle)
        if mismatch_key and mismatch_key != self._last_mismatch_key:
            self._last_mismatch_key = mismatch_key
            submission = self._build_recovery_strain_mismatch(recovery, cycle)
            if submission is not None:
                submissions.append(submission)

        return submissions

    def _iter_items(self, summary: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        items: list[tuple[str, dict[str, Any]]] = []
        for kind, key in (
            ("recovery", "latest_recovery"),
            ("sleep", "latest_sleep"),
            ("cycle", "latest_cycle"),
        ):
            item = self._dict_or_none(summary.get(key))
            if item and self._is_scored(item):
                items.append((kind, item))

        workouts = summary.get("recent_workouts")
        if isinstance(workouts, list):
            for workout in workouts:
                item = self._dict_or_none(workout)
                if item and self._is_scored(item):
                    items.append(("workout", item))
        return items

    def _submission_for(self, kind: str, item: dict[str, Any]) -> PreparedSubmission | None:
        if kind == "recovery":
            return self._build_recovery_submission(item)
        if kind == "sleep":
            return self._build_sleep_submission(item)
        if kind == "workout":
            return self._build_workout_submission(item)
        if kind == "cycle":
            return self._build_cycle_submission(item)
        return None

    def _build_snapshot(self, summary: dict[str, Any]) -> str:
        parts: list[str] = ["WHOOP current snapshot:"]

        recovery = self._dict_or_none(summary.get("latest_recovery"))
        if recovery and self._is_scored(recovery):
            score = self._dict_or_none(recovery.get("score")) or {}
            parts.append(
                self._compact_sentence(
                    "recovery",
                    [
                        self._fmt_percent(score.get("recovery_score")),
                        self._fmt_bpm("RHR", score.get("resting_heart_rate")),
                        self._fmt_number("HRV", score.get("hrv_rmssd_milli"), "ms", decimals=1),
                    ],
                )
            )

        sleep = self._dict_or_none(summary.get("latest_sleep"))
        if sleep and self._is_scored(sleep):
            score = self._dict_or_none(sleep.get("score")) or {}
            stage = self._dict_or_none(score.get("stage_summary")) or {}
            parts.append(
                self._compact_sentence(
                    "sleep",
                    [
                        self._fmt_percent(score.get("sleep_performance_percentage"), label="performance"),
                        self._fmt_duration(self._as_float(stage.get("total_in_bed_time_milli")), label="in bed"),
                        self._fmt_duration(self._sleep_time_milli(stage), label="asleep"),
                    ],
                )
            )

        cycle = self._dict_or_none(summary.get("latest_cycle"))
        if cycle and self._is_scored(cycle):
            score = self._dict_or_none(cycle.get("score")) or {}
            parts.append(
                self._compact_sentence(
                    "day strain",
                    [
                        self._fmt_number(None, score.get("strain"), None, decimals=1),
                        self._fmt_bpm("avg HR", score.get("average_heart_rate")),
                    ],
                )
            )

        workouts = [item for kind, item in self._iter_items(summary) if kind == "workout"]
        if workouts:
            workout = workouts[0]
            score = self._dict_or_none(workout.get("score")) or {}
            parts.append(
                self._compact_sentence(
                    "latest workout",
                    [
                        str(workout.get("sport_name") or "workout"),
                        self._fmt_number(None, score.get("strain"), "strain", decimals=1),
                    ],
                )
            )

        if len(parts) == 1:
            return ""
        return " ".join(parts)

    def _build_recovery_submission(self, recovery: dict[str, Any]) -> PreparedSubmission | None:
        score = self._dict_or_none(recovery.get("score"))
        if not score:
            return None

        recovery_score = self._as_float(score.get("recovery_score"))
        parts = [
            self._fmt_percent(recovery_score, label="recovery"),
            self._fmt_bpm("RHR", score.get("resting_heart_rate")),
            self._fmt_number("HRV", score.get("hrv_rmssd_milli"), "ms", decimals=1),
            self._fmt_percent(score.get("spo2_percentage"), label="SpO2"),
            self._fmt_number("skin temp", score.get("skin_temp_celsius"), "C", decimals=1),
        ]
        content = f"WHOOP recovery scored: {self._join_parts(parts)}."
        priority = _PRIORITY_HIGH if recovery_score is not None and recovery_score < LOW_RECOVERY_THRESHOLD else _PRIORITY_DEFAULT
        return PreparedSubmission(text=content, priority=priority)

    def _build_sleep_submission(self, sleep: dict[str, Any]) -> PreparedSubmission | None:
        score = self._dict_or_none(sleep.get("score"))
        if not score:
            return None
        stage = self._dict_or_none(score.get("stage_summary")) or {}

        asleep_milli = self._sleep_time_milli(stage)
        performance = self._as_float(score.get("sleep_performance_percentage"))
        parts = [
            self._fmt_percent(performance, label="performance"),
            self._fmt_percent(score.get("sleep_consistency_percentage"), label="consistency"),
            self._fmt_percent(score.get("sleep_efficiency_percentage"), label="efficiency"),
            self._fmt_duration(asleep_milli, label="asleep"),
            self._fmt_duration(self._as_float(stage.get("total_in_bed_time_milli")), label="in bed"),
            self._fmt_duration(self._as_float(stage.get("total_rem_sleep_time_milli")), label="REM"),
            self._fmt_duration(self._as_float(stage.get("total_slow_wave_sleep_time_milli")), label="SWS"),
            self._fmt_duration(self._as_float(stage.get("total_awake_time_milli")), label="awake"),
            self._fmt_int(stage.get("disturbance_count"), label="disturbances"),
        ]
        content = f"WHOOP sleep scored: {self._join_parts(parts)}."
        high = (performance is not None and performance < LOW_SLEEP_PERFORMANCE_THRESHOLD) or (
            asleep_milli is not None and asleep_milli < SHORT_SLEEP_MILLI
        )
        return PreparedSubmission(text=content, priority=_PRIORITY_HIGH if high else _PRIORITY_DEFAULT)

    def _build_workout_submission(self, workout: dict[str, Any]) -> PreparedSubmission | None:
        score = self._dict_or_none(workout.get("score"))
        if not score:
            return None

        strain = self._as_float(score.get("strain"))
        duration = self._duration_between(workout.get("start"), workout.get("end"))
        parts = [
            str(workout.get("sport_name") or "workout"),
            self._fmt_duration(duration, label=None),
            self._fmt_number(None, strain, "strain", decimals=1),
            self._fmt_bpm("avg HR", score.get("average_heart_rate")),
            self._fmt_bpm("max HR", score.get("max_heart_rate")),
            self._fmt_number(None, score.get("kilojoule"), "kJ", decimals=0),
            self._fmt_percent(score.get("percent_recorded"), label="recorded"),
            self._fmt_distance(score.get("distance_meter")),
            self._format_zones(self._dict_or_none(score.get("zone_durations"))),
        ]
        content = f"WHOOP workout: {self._join_parts(parts)}."
        priority = _PRIORITY_HIGH if strain is not None and strain >= HIGH_STRAIN_THRESHOLD else _PRIORITY_DEFAULT
        return PreparedSubmission(text=content, priority=priority)

    def _build_cycle_submission(self, cycle: dict[str, Any]) -> PreparedSubmission | None:
        score = self._dict_or_none(cycle.get("score"))
        if not score:
            return None

        open_label = "open cycle" if not cycle.get("end") else "closed cycle"
        parts = [
            self._fmt_number("day strain", score.get("strain"), None, decimals=1),
            self._fmt_bpm("avg HR", score.get("average_heart_rate")),
            self._fmt_bpm("max HR", score.get("max_heart_rate")),
            self._fmt_number(None, score.get("kilojoule"), "kJ", decimals=0),
            open_label,
        ]
        return PreparedSubmission(text=f"WHOOP cycle strain updated: {self._join_parts(parts)}.")

    def _build_recovery_strain_mismatch(
        self,
        recovery: dict[str, Any] | None,
        cycle: dict[str, Any] | None,
    ) -> PreparedSubmission | None:
        if not recovery or not cycle:
            return None
        recovery_score = self._as_float((self._dict_or_none(recovery.get("score")) or {}).get("recovery_score"))
        strain = self._as_float((self._dict_or_none(cycle.get("score")) or {}).get("strain"))
        if recovery_score is None or strain is None:
            return None
        if recovery_score >= LOW_RECOVERY_THRESHOLD or strain < HIGH_STRAIN_THRESHOLD:
            return None
        content = f"WHOOP load/recovery mismatch: {recovery_score:.0f}% recovery with {strain:.1f} day strain."
        return PreparedSubmission(text=content, priority=_PRIORITY_HIGH)

    def _mismatch_key(self, recovery: dict[str, Any] | None, cycle: dict[str, Any] | None) -> str | None:
        mismatch = self._build_recovery_strain_mismatch(recovery, cycle)
        if mismatch is None:
            return None
        recovery_score = (self._dict_or_none(recovery.get("score")) or {}).get("recovery_score") if recovery else None
        strain = (self._dict_or_none(cycle.get("score")) or {}).get("strain") if cycle else None
        return f"{recovery.get('cycle_id')}:{cycle.get('id')}:{recovery_score}:{strain}" if recovery and cycle else None

    def _fingerprint(self, kind: str, item: dict[str, Any]) -> str:
        if kind == "recovery":
            score = self._dict_or_none(item.get("score")) or {}
            basis = {
                "kind": kind,
                "cycle_id": item.get("cycle_id"),
                "updated_at": item.get("updated_at"),
                "recovery_score": score.get("recovery_score"),
                "resting_heart_rate": score.get("resting_heart_rate"),
                "hrv_rmssd_milli": score.get("hrv_rmssd_milli"),
            }
        elif kind in {"sleep", "workout"}:
            score = self._dict_or_none(item.get("score")) or {}
            basis = {"kind": kind, "id": item.get("id"), "updated_at": item.get("updated_at"), "score": score}
        elif kind == "cycle":
            score = self._dict_or_none(item.get("score")) or {}
            basis = {
                "kind": kind,
                "id": item.get("id"),
                "updated_at": item.get("updated_at"),
                "strain": score.get("strain"),
                "average_heart_rate": score.get("average_heart_rate"),
                "max_heart_rate": score.get("max_heart_rate"),
            }
        else:
            basis = {"kind": kind, "item": item}
        raw = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_scored(item: dict[str, Any]) -> bool:
        return str(item.get("score_state") or "").upper() == "SCORED" and isinstance(item.get("score"), dict)

    @staticmethod
    def _dict_or_none(value: Any) -> dict[str, Any] | None:
        return value if isinstance(value, dict) else None

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _fmt_percent(value: Any, *, label: str | None = None) -> str:
        numeric = WhoopBackgroundWorker._as_float(value)
        if numeric is None:
            return ""
        rendered = f"{numeric:.0f}%"
        return f"{rendered} {label}" if label else rendered

    @staticmethod
    def _fmt_bpm(label: str, value: Any) -> str:
        numeric = WhoopBackgroundWorker._as_float(value)
        if numeric is None:
            return ""
        return f"{label} {numeric:.0f} bpm"

    @staticmethod
    def _fmt_number(label: str | None, value: Any, unit: str | None, *, decimals: int) -> str:
        numeric = WhoopBackgroundWorker._as_float(value)
        if numeric is None:
            return ""
        rendered = f"{numeric:.{decimals}f}"
        if unit:
            rendered = f"{rendered} {unit}"
        return f"{label} {rendered}" if label else rendered

    @staticmethod
    def _fmt_int(value: Any, *, label: str) -> str:
        numeric = WhoopBackgroundWorker._as_float(value)
        if numeric is None:
            return ""
        return f"{numeric:.0f} {label}"

    @staticmethod
    def _fmt_duration(value: Any, *, label: str | None) -> str:
        milli = WhoopBackgroundWorker._as_float(value)
        if milli is None:
            return ""
        total_minutes = max(0, int(round(milli / 60_000)))
        hours, minutes = divmod(total_minutes, 60)
        if hours:
            rendered = f"{hours}h{minutes:02d}m"
        else:
            rendered = f"{minutes}m"
        return f"{rendered} {label}" if label else rendered

    @staticmethod
    def _fmt_distance(value: Any) -> str:
        meters = WhoopBackgroundWorker._as_float(value)
        if meters is None:
            return ""
        if meters >= 1000:
            return f"{meters / 1000:.2f} km"
        return f"{meters:.0f} m"

    @staticmethod
    def _duration_between(start: Any, end: Any) -> float | None:
        from datetime import datetime

        if not isinstance(start, str) or not isinstance(end, str):
            return None
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError:
            return None
        return max(0.0, (end_dt - start_dt).total_seconds() * 1000)

    @staticmethod
    def _sleep_time_milli(stage: dict[str, Any]) -> float | None:
        values = [
            WhoopBackgroundWorker._as_float(stage.get("total_light_sleep_time_milli")),
            WhoopBackgroundWorker._as_float(stage.get("total_slow_wave_sleep_time_milli")),
            WhoopBackgroundWorker._as_float(stage.get("total_rem_sleep_time_milli")),
        ]
        present = [value for value in values if value is not None]
        if not present:
            return None
        return sum(present)

    @staticmethod
    def _format_zones(zones: dict[str, Any] | None) -> str:
        if not zones:
            return ""
        ordered = [
            ("Z5", zones.get("zone_five_milli")),
            ("Z4", zones.get("zone_four_milli")),
            ("Z3", zones.get("zone_three_milli")),
            ("Z2", zones.get("zone_two_milli")),
        ]
        rendered = [
            f"{label} {WhoopBackgroundWorker._fmt_duration(value, label=None)}"
            for label, value in ordered
            if WhoopBackgroundWorker._as_float(value)
        ]
        return "zones " + ", ".join(rendered) if rendered else ""

    @staticmethod
    def _join_parts(parts: list[str]) -> str:
        return ", ".join(part for part in parts if part)

    @staticmethod
    def _compact_sentence(label: str, parts: list[str]) -> str:
        body = WhoopBackgroundWorker._join_parts(parts)
        return f"{label}: {body}." if body else ""
