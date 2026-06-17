from __future__ import annotations

from dataclasses import dataclass, field
import os
import time
from typing import Any

from truffle.app.background_pb2 import BackgroundContext
from truffile.app_runtime import BackgroundWorkerApp

from location_context import CoarseLocation, env_int, get_cached_user_location


_PRIORITY_LOW = getattr(BackgroundContext, "PRIORITY_LOW", 0)


@dataclass(slots=True)
class ViatorLocationDigest:
    content: str = ""
    priority: int = _PRIORITY_LOW
    uris: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


class ViatorLocationBackgroundWorker:
    def __init__(self) -> None:
        self._last_submission_at = 0.0
        self._last_location_key = ""

    def verify(self) -> tuple[bool, str]:
        location = get_cached_user_location(fetch_if_missing=False)
        if location:
            return True, f"Viator location background ready: {location.label()}"
        return True, "Viator location background ready; no cached location yet"

    def run_cycle(self) -> ViatorLocationDigest:
        fetch_location = os.getenv("VIATOR_BG_FETCH_IP_LOCATION", "1").strip() != "0"
        location = get_cached_user_location(fetch_if_missing=fetch_location)
        cadence_hours = env_int("VIATOR_BG_LOCATION_HINT_HOURS", 24, minimum=1)
        if not location:
            return ViatorLocationDigest(
                stats={"submitted": False, "reason": "no_location", "location": "", "cadence_hours": cadence_hours}
            )

        now = time.time()
        location_key = location.label()
        if (
            self._last_submission_at > 0
            and self._last_location_key == location_key
            and now - self._last_submission_at < cadence_hours * 3600
        ):
            return ViatorLocationDigest(
                stats={
                    "submitted": False,
                    "reason": "cadence_gate",
                    "location": location_key,
                    "cadence_hours": cadence_hours,
                }
            )

        self._last_submission_at = now
        self._last_location_key = location_key
        return ViatorLocationDigest(
            content=self._build_location_context(location, cadence_hours=cadence_hours),
            stats={"submitted": True, "location": location_key, "cadence_hours": cadence_hours},
        )

    @staticmethod
    def _build_location_context(location: CoarseLocation, *, cadence_hours: int) -> str:
        destination = location.destination()
        coordinates = ""
        if location.lat is not None and location.lon is not None:
            coordinates = f" lat={location.lat} lon={location.lon}"
        return "\n".join(
            [
                f"Viator local travel context: user appears near {location.label()} (cadence={cadence_hours}h).",
                f"coarse_location city=\"{location.city}\" region=\"{location.region}\" country=\"{location.country}\" zip=\"{location.zip}\" timezone=\"{location.timezone}\"{coordinates}",
                (
                    "Actions you can do with this: use search_experiences with "
                    f"searchTerm=\"things to do near {destination}\" and the user's relevant dates, "
                    "then use get_experience_details for promising codes before recommending tours or activities."
                ),
                (
                    "Good background follow-up: suggest nearby weekend activities, day trips, family-friendly tours, "
                    "or rainy-day options only when useful to the user's current context."
                ),
            ]
        )


class ViatorBackgroundApp(BackgroundWorkerApp[ViatorLocationBackgroundWorker, ViatorLocationDigest]):
    def __init__(self) -> None:
        super().__init__("viator", logger_name="viator.background")

    def build_worker(self) -> ViatorLocationBackgroundWorker:
        return ViatorLocationBackgroundWorker()

    def verify_worker(self, worker: ViatorLocationBackgroundWorker) -> tuple[bool, str]:
        return worker.verify()

    def run_cycle(self, worker: ViatorLocationBackgroundWorker) -> ViatorLocationDigest:
        return worker.run_cycle()

    def handle_cycle_result(self, ctx: object, result: ViatorLocationDigest) -> None:
        if not result.content:
            self.logger.info("Viator location background produced no submission", extra={"stats": result.stats})
            return
        self.submit_text(ctx, content=result.content, priority=result.priority, uris=result.uris)


app = ViatorBackgroundApp()


if __name__ == "__main__":
    app.main()
