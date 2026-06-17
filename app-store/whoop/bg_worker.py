from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable

from truffile.app_runtime.errors import AppAuthError

from whoop_auth import WhoopOAuth
from whoop_client import WhoopClient

_ACTION_HINT = (
    "Actions you can do with this: use WHOOP foreground tools to inspect sleep, recovery, cycles, "
    "workouts, and body measurements; summarize health trends; or compare changes against the user's recent activity."
)


@dataclass
class BackgroundDigest:
    generated_at: str
    baseline_digest: str = ""
    delta_digest: str = ""
    seeded: bool = False
    changes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


class WhoopBackgroundWorker:
    def __init__(
        self,
        auth: WhoopOAuth | None = None,
        client: WhoopClient | None = None,
    ) -> None:
        self.auth = auth or WhoopOAuth()
        self.client = client or WhoopClient(auth=self.auth)
        self._is_seeded = False
        self._last_scan_at: datetime | None = None
        self._seen: dict[str, dict[str, str]] = {
            "sleep": {},
            "workouts": {},
            "recovery": {},
            "cycles": {},
        }

    async def close(self) -> None:
        await self.client.close()

    async def reset_clients(self) -> None:
        try:
            await self.close()
        except Exception:
            pass
        self.auth = WhoopOAuth()
        self.client = WhoopClient(auth=self.auth)

    async def verify(self) -> tuple[bool, str]:
        try:
            return await self.client.verify()
        except Exception as exc:
            return False, f"WHOOP background auth failed: {exc}"

    async def run_cycle(self) -> BackgroundDigest:
        now = datetime.now(UTC).replace(microsecond=0)
        generated_at = now.isoformat()
        lookback_days = self._env_int("WHOOP_BG_LOOKBACK_DAYS", 14)
        overlap_hours = self._env_int("WHOOP_BG_OVERLAP_HOURS", 2)
        scan_limit = min(25, self._env_int("WHOOP_BG_SCAN_LIMIT", 25))
        start_at = self._scan_start(now, lookback_days=lookback_days, overlap_hours=overlap_hours)

        warnings: list[str] = []
        try:
            ok, message = await self.client.verify()
            if not ok:
                return BackgroundDigest(generated_at=generated_at, error="auth_failure", warnings=[message])

            profile = await self._safe_call("profile", self.client.get_profile_basic(), warnings)
            body = await self._safe_call("body_measurements", self.client.get_body_measurements(), warnings)
            scanned = {
                "sleep": await self._fetch_records(
                    "sleep",
                    self.client.list_sleep,
                    start=start_at,
                    end=now,
                    limit=scan_limit,
                    warnings=warnings,
                ),
                "workouts": await self._fetch_records(
                    "workouts",
                    self.client.list_workouts,
                    start=start_at,
                    end=now,
                    limit=scan_limit,
                    warnings=warnings,
                ),
                "recovery": await self._fetch_records(
                    "recovery",
                    self.client.list_recovery,
                    start=start_at,
                    end=now,
                    limit=scan_limit,
                    warnings=warnings,
                ),
                "cycles": await self._fetch_records(
                    "cycles",
                    self.client.list_cycles,
                    start=start_at,
                    end=now,
                    limit=scan_limit,
                    warnings=warnings,
                ),
            }
        except AppAuthError as exc:
            return BackgroundDigest(generated_at=generated_at, error="auth_failure", warnings=[str(exc)])
        except Exception as exc:
            return BackgroundDigest(generated_at=generated_at, error=str(exc))

        changes = self._record_changes(scanned, emit=bool(self._is_seeded))
        self._last_scan_at = now

        stats = {
            "lookback_days": lookback_days,
            "overlap_hours": overlap_hours,
            "scan_limit": scan_limit,
            "scan_start": start_at.isoformat(),
            "sleep": len(scanned["sleep"]),
            "workouts": len(scanned["workouts"]),
            "recovery": len(scanned["recovery"]),
            "cycles": len(scanned["cycles"]),
            "warnings": len(warnings),
        }

        if not self._is_seeded:
            self._is_seeded = True
            baseline_digest = self._build_baseline_digest(
                generated_at=generated_at,
                profile=profile if isinstance(profile, dict) else {},
                body=body if isinstance(body, dict) else {},
                scanned=scanned,
                lookback_days=lookback_days,
                warnings=warnings,
            )
            return BackgroundDigest(
                generated_at=generated_at,
                baseline_digest=baseline_digest,
                seeded=True,
                warnings=warnings,
                stats=stats,
            )

        delta_digest = self._build_delta_digest(
            generated_at=generated_at,
            changes=changes,
            warnings=warnings,
        )
        return BackgroundDigest(
            generated_at=generated_at,
            delta_digest=delta_digest,
            changes=changes,
            warnings=warnings,
            stats=stats | {"changes": sum(len(items) for items in changes.values())},
        )

    async def _safe_call(
        self,
        label: str,
        awaitable: Awaitable[dict[str, Any]],
        warnings: list[str],
    ) -> dict[str, Any]:
        try:
            return await awaitable
        except AppAuthError:
            raise
        except Exception as exc:
            warnings.append(f"{label}: {exc}")
            return {}

    async def _fetch_records(
        self,
        label: str,
        method: Callable[..., Awaitable[dict[str, Any]]],
        *,
        start: datetime,
        end: datetime,
        limit: int,
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        try:
            payload = await method(
                limit=limit,
                start=start.isoformat().replace("+00:00", "Z"),
                end=end.isoformat().replace("+00:00", "Z"),
            )
        except AppAuthError:
            raise
        except Exception as exc:
            warnings.append(f"{label}: {exc}")
            return []
        records = payload.get("records")
        if not isinstance(records, list):
            return []
        return [record for record in records if isinstance(record, dict)]

    def _record_changes(
        self,
        scanned: dict[str, list[dict[str, Any]]],
        *,
        emit: bool,
    ) -> dict[str, list[dict[str, Any]]]:
        changes: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in self._seen}
        for bucket, records in scanned.items():
            seen_bucket = self._seen.setdefault(bucket, {})
            for record in records:
                key = self._record_key(bucket, record)
                fingerprint = self._fingerprint(record)
                previous = seen_bucket.get(key)
                seen_bucket[key] = fingerprint
                if emit and previous != fingerprint:
                    changed = dict(record)
                    changed["_change_type"] = "new" if previous is None else "updated"
                    changed["_whoop_bg_key"] = key
                    changes.setdefault(bucket, []).append(changed)
        return changes

    def _scan_start(self, now: datetime, *, lookback_days: int, overlap_hours: int) -> datetime:
        if self._last_scan_at is None:
            return now - timedelta(days=lookback_days)
        return self._last_scan_at - timedelta(hours=overlap_hours)

    def _build_baseline_digest(
        self,
        *,
        generated_at: str,
        profile: dict[str, Any],
        body: dict[str, Any],
        scanned: dict[str, list[dict[str, Any]]],
        lookback_days: int,
        warnings: list[str],
    ) -> str:
        lines = [
            (
                f"WHOOP baseline ({generated_at[:10]}): tracked {len(scanned['sleep'])} sleep, "
                f"{len(scanned['workouts'])} workout, {len(scanned['recovery'])} recovery, "
                f"and {len(scanned['cycles'])} cycle record(s) from the last {lookback_days} day(s)."
            ),
            "Future WHOOP background runs happen every 12 hours and submit only new or changed records after this baseline scan.",
            _ACTION_HINT,
        ]

        profile_line = self._profile_line(profile, body)
        if profile_line:
            lines.extend(["", profile_line])

        latest_sections = [
            ("Latest sleep", self._latest(scanned["sleep"]), "sleep"),
            ("Latest workout", self._latest(scanned["workouts"]), "workout"),
            ("Latest recovery", self._latest(scanned["recovery"]), "recovery"),
            ("Latest cycle", self._latest(scanned["cycles"]), "cycle"),
        ]
        for title, record, kind in latest_sections:
            if record:
                lines.append(f"{title}: {self._record_summary(kind, record)}")

        if warnings:
            lines.extend(["", "Partial scan warnings:"])
            lines.extend(f"- {warning}" for warning in warnings[:4])
        return "\n".join(lines).strip()

    def _build_delta_digest(
        self,
        *,
        generated_at: str,
        changes: dict[str, list[dict[str, Any]]],
        warnings: list[str],
    ) -> str:
        total = sum(len(items) for items in changes.values())
        if total <= 0:
            return ""

        lines = [
            f"WHOOP health digest ({generated_at[:10]}): {total} new or updated record(s) since the last scan.",
            _ACTION_HINT,
        ]
        for bucket, title, kind in (
            ("sleep", "Sleep changes", "sleep"),
            ("workouts", "Workout changes", "workout"),
            ("recovery", "Recovery changes", "recovery"),
            ("cycles", "Cycle changes", "cycle"),
        ):
            records = changes.get(bucket) or []
            if not records:
                continue
            lines.extend(["", f"{title}:"])
            for record in sorted(records, key=self._record_sort_key, reverse=True)[:8]:
                change_type = str(record.get("_change_type") or "changed")
                lines.append(f"- {change_type}: {self._record_summary(kind, record)}")
            if len(records) > 8:
                lines.append(f"- ... {len(records) - 8} more")

        if warnings:
            lines.extend(["", "Partial scan warnings:"])
            lines.extend(f"- {warning}" for warning in warnings[:4])
        return "\n".join(lines).strip()

    @staticmethod
    def _profile_line(profile: dict[str, Any], body: dict[str, Any]) -> str:
        name = " ".join(
            part
            for part in (
                str(profile.get("first_name") or "").strip(),
                str(profile.get("last_name") or "").strip(),
            )
            if part
        )
        bits = []
        if name:
            bits.append(name)
        if profile.get("user_id") is not None:
            bits.append(f"user_id={profile.get('user_id')}")
        height = body.get("height_cm") or body.get("height_meter")
        weight = body.get("weight_kg") or body.get("weight_kilogram")
        max_hr = body.get("max_heart_rate")
        if height is not None:
            bits.append(f"height={height}")
        if weight is not None:
            bits.append(f"weight={weight}")
        if max_hr is not None:
            bits.append(f"max_hr={max_hr}")
        return "Profile baseline: " + ", ".join(bits) if bits else ""

    @classmethod
    def _record_summary(cls, kind: str, record: dict[str, Any]) -> str:
        label = cls._first_present(record, ("id", "cycle_id", "sleep_id", "workout_id")) or cls._record_key(kind, record)
        bits = [str(label)]
        for key in ("start", "end", "updated_at", "timezone_offset"):
            value = cls._compact(record.get(key))
            if value:
                bits.append(f"{key}={value}")
        for key in cls._metric_keys(kind):
            value = cls._score_value(record, key)
            if value not in (None, "", [], {}):
                bits.append(f"{key}={value}")
        return "; ".join(bits[:12])

    @staticmethod
    def _metric_keys(kind: str) -> tuple[str, ...]:
        if kind == "sleep":
            return (
                "sleep_performance_percentage",
                "sleep_efficiency_percentage",
                "respiratory_rate",
                "nap",
            )
        if kind == "workout":
            return ("strain", "average_heart_rate", "max_heart_rate", "kilojoule", "sport_id", "sport_name")
        if kind == "recovery":
            return ("recovery_score", "resting_heart_rate", "hrv_rmssd_milli", "spo2_percentage", "skin_temp_celsius")
        return ("strain", "average_heart_rate", "max_heart_rate")

    @staticmethod
    def _score_value(record: dict[str, Any], key: str) -> Any:
        score = record.get("score")
        if isinstance(score, dict) and score.get(key) not in (None, "", [], {}):
            return score.get(key)
        return record.get(key)

    @staticmethod
    def _first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            value = data.get(key)
            if value not in (None, "", [], {}):
                return value
        return None

    @classmethod
    def _latest(cls, records: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not records:
            return None
        return max(records, key=cls._record_sort_key)

    @staticmethod
    def _record_sort_key(record: dict[str, Any]) -> str:
        for key in ("updated_at", "end", "start", "created_at"):
            value = str(record.get(key) or "")
            if value:
                return value
        return ""

    @classmethod
    def _record_key(cls, bucket: str, record: dict[str, Any]) -> str:
        value = cls._first_present(record, ("id", "cycle_id", "sleep_id", "workout_id"))
        if value not in (None, "", [], {}):
            return f"{bucket}:{value}"
        start = str(record.get("start") or "")
        end = str(record.get("end") or "")
        return f"{bucket}:{hashlib.sha256(f'{start}:{end}:{cls._stable_json(record)}'.encode()).hexdigest()[:16]}"

    @staticmethod
    def _fingerprint(record: dict[str, Any]) -> str:
        return hashlib.sha256(WhoopBackgroundWorker._stable_json(record).encode("utf-8")).hexdigest()

    @staticmethod
    def _stable_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

    @staticmethod
    def _compact(value: Any) -> str:
        if value in (None, "", [], {}):
            return ""
        return " ".join(str(value).split())

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        try:
            return max(1, int(os.getenv(name, str(default)).strip()))
        except ValueError:
            return default
