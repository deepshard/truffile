from __future__ import annotations

import asyncio
import atexit
from concurrent.futures import Future
import queue
import threading
from typing import Any

from truffile.app_runtime import BackgroundApp
from truffle.app.background_pb2 import BackgroundContext

from bg_worker import BackgroundDigest, WhoopBackgroundWorker
from whoop_auth import WhoopOAuth

_PRIORITY_DEFAULT = getattr(
    BackgroundContext,
    "PRIORITY_DEFAULT",
    getattr(BackgroundContext, "PRIORITY_HIGH", 1),
)
_PRIORITY_LOW = getattr(BackgroundContext, "PRIORITY_LOW", 0)
_LOOP_STOP = object()


def _close_coro(coro: Any) -> None:
    close = getattr(coro, "close", None)
    if callable(close):
        close()


class WhoopBackgroundApp(BackgroundApp[WhoopBackgroundWorker, BackgroundDigest]):
    def __init__(self) -> None:
        super().__init__("whoop", logger_name="whoop.background")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_queue: queue.Queue[Any] | None = None
        self._loop_thread: threading.Thread | None = None
        self._loop_thread_id: int | None = None

    def _ensure_loop(self) -> queue.Queue[Any]:
        if self._loop_queue is not None and self._loop_thread is not None and self._loop_thread.is_alive():
            return self._loop_queue

        loop = asyncio.new_event_loop()
        work_queue: queue.Queue[Any] = queue.Queue()
        ready = threading.Event()

        def _run_loop() -> None:
            asyncio.set_event_loop(loop)
            self._loop_thread_id = threading.get_ident()
            ready.set()
            while True:
                item = work_queue.get()
                if item is _LOOP_STOP:
                    break
                coro, future = item
                if not future.set_running_or_notify_cancel():
                    _close_coro(coro)
                    continue
                try:
                    future.set_result(loop.run_until_complete(coro))
                except BaseException as exc:  # noqa: BLE001
                    future.set_exception(exc)
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())

        thread = threading.Thread(target=_run_loop, name="whoop-bg-loop", daemon=True)
        thread.start()
        ready.wait()
        self._loop = loop
        self._loop_queue = work_queue
        self._loop_thread = thread
        return work_queue

    def _run(self, coro: Any) -> Any:
        work_queue = self._ensure_loop()
        if threading.get_ident() == self._loop_thread_id:
            _close_coro(coro)
            raise RuntimeError("WHOOP background runner cannot block its own event loop")

        future: Future[Any] = Future()
        work_queue.put((coro, future))
        return future.result()

    def build_worker(self) -> WhoopBackgroundWorker:
        return WhoopBackgroundWorker(WhoopOAuth())

    def verify_worker(self, worker: WhoopBackgroundWorker) -> tuple[bool, str]:
        self._run(worker.reset_clients())
        return self._run(worker.verify())

    def run_cycle(self, worker: WhoopBackgroundWorker) -> BackgroundDigest:
        # Background workers are checkpointed between cycles; rebuild network
        # clients so restored HTTP transports are never reused.
        self._run(worker.reset_clients())
        try:
            return self._run(worker.run_cycle())
        finally:
            try:
                self._run(worker.close())
            except Exception:
                self.logger.exception("Failed to close WHOOP clients after cycle")

    def handle_cycle_result(self, ctx: Any, result: BackgroundDigest) -> None:
        if result.error:
            self.logger.error("WHOOP background cycle failed", extra={"error": result.error})
            if result.error == "auth_failure":
                self.report_auth_failure(ctx, result.error)
            return

        self.reset_auth_failures()

        if result.seeded:
            if result.baseline_digest:
                self._safe_submit_text(ctx, content=result.baseline_digest, priority=_PRIORITY_LOW)
            else:
                self.logger.info("WHOOP background seed cycle complete with no baseline digest")
            return

        if result.delta_digest:
            self._safe_submit_text(ctx, content=result.delta_digest, priority=_PRIORITY_DEFAULT)
            return

        self.logger.info("WHOOP background cycle completed with no new or updated records")

    def _safe_submit_text(self, ctx: Any, *, content: str, priority: int) -> None:
        try:
            self.submit_text(ctx, content=content, priority=priority)
        except Exception as exc:
            self.logger.warning("WHOOP submit_context failed; suppressing runtime error: %s", exc)

    def close(self) -> None:
        worker = self._worker
        if worker is not None:
            try:
                self._run(worker.close())
            except Exception:
                self.logger.exception("Failed to close WHOOP background worker")
        self._worker = None
        self._stop_loop()

    def _stop_loop(self) -> None:
        loop = self._loop
        work_queue = self._loop_queue
        thread = self._loop_thread
        self._loop = None
        self._loop_queue = None
        self._loop_thread = None
        self._loop_thread_id = None
        if loop is None or work_queue is None:
            return
        work_queue.put(_LOOP_STOP)
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)
        if not loop.is_closed():
            loop.close()

    def reset_for_test(self) -> None:
        self.close()
        super().reset_for_test()


app = WhoopBackgroundApp()


def _cleanup() -> None:
    app.close()


if __name__ == "__main__":
    atexit.register(_cleanup)
    app.main()
