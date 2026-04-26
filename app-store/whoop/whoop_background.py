# Draft background app shell. It is intentionally not enabled in truffile.yaml
# for the foreground-only PR.
"""Background WHOOP app shell."""

from __future__ import annotations

import atexit
import asyncio
import threading
from typing import Any

from truffile.app_runtime import BackgroundWorkerApp

from whoop_bg_worker import BgRunResult, WhoopBackgroundWorker


class WhoopBackgroundApp(BackgroundWorkerApp[WhoopBackgroundWorker, BgRunResult]):
    def __init__(self) -> None:
        super().__init__("whoop", logger_name="whoop.background")
        self._loop: asyncio.AbstractEventLoop | None = None

    def _run(self, coro: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
            return self._loop.run_until_complete(coro)

        result: dict[str, Any] = {}
        error: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except BaseException as exc:  # noqa: BLE001
                error["exc"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if "exc" in error:
            raise error["exc"]
        return result.get("value")

    def build_worker(self) -> WhoopBackgroundWorker:
        return WhoopBackgroundWorker()

    def verify_worker(self, worker: WhoopBackgroundWorker) -> tuple[bool, str]:
        return self._run(worker.verify())

    def run_cycle(self, worker: WhoopBackgroundWorker) -> BgRunResult:
        return self._run(worker.run_cycle())

    def handle_cycle_result(self, ctx: object, result: BgRunResult) -> None:
        if result.auth_error:
            self.report_auth_failure(ctx, result.auth_error)
            return

        self.reset_auth_failures()
        if result.error:
            self.logger.error("WHOOP background cycle failed: %s", result.error)
            return

        if not result.submissions:
            self.logger.info("WHOOP background cycle produced no new signals")
            return

        for submission in result.submissions:
            self.submit_text(
                ctx,
                content=submission.text,
                uris=submission.uris,
                priority=submission.priority,
            )

    def reset_for_test(self) -> None:
        worker = getattr(self, "_worker", None)
        if worker is not None:
            try:
                self._run(worker.close())
            except Exception:
                self.logger.exception("Failed to close WHOOP background worker during reset")
        super().reset_for_test()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()
        self._loop = None

    def cleanup(self) -> None:
        self.reset_for_test()


app = WhoopBackgroundApp()


atexit.register(app.cleanup)


if __name__ == "__main__":
    app.main()
