from __future__ import annotations

import atexit
import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from truffle.app.background_pb2 import BackgroundContext
from truffile.app_runtime import BackgroundWorkerApp
from truffile.app_runtime.errors import AppAuthError, AppRuntimeFailure

from bg_worker import DigestRunResult, NotionBackgroundWorker


LOGGER = logging.getLogger("notion.background")
LOGGER.setLevel(logging.INFO)

_PRIORITY_DEFAULT = getattr(
    BackgroundContext,
    "PRIORITY_DEFAULT",
    getattr(BackgroundContext, "PRIORITY_HIGH", 1),
)
_PRIORITY_LOW = getattr(BackgroundContext, "PRIORITY_LOW", 0)


@dataclass(frozen=True, slots=True)
class NotionCycleResult:
    summary: str | None = None
    priority: int = _PRIORITY_LOW
    digest_hash: str = ""
    stats: dict[str, Any] = field(default_factory=dict)
    auth_error: str | None = None
    error: str | None = None
    uris: list[str] = field(default_factory=list)


class _StubNotionBackgroundWorker:
    def verify(self) -> tuple[bool, str]:
        return True, "Notion MCP verified. tools=notion_search,notion_fetch"

    def close(self) -> None:
        return None

    def run_cycle(self) -> DigestRunResult:
        summary = (
            "Notion changes since 2026-06-08T12:00:00+00:00: 1 edited page/database item(s).\n"
            "stats: source=stub, scanned=1, changed=1, checked_at=2026-06-08T12:30:00+00:00\n"
            "Open with notion_fetch(url=...) or notion_fetch(id=...).\n\n"
            "Edited pages/databases:\n"
            '- Roadmap (page) edited=2026-06-08T12:20:00Z by=Abd target=https://notion.so/roadmap '
            'open={"tool":"notion_fetch","arguments":{"url":"https://notion.so/roadmap"}}'
        )
        return DigestRunResult(
            summary=summary,
            stats={"source": "stub", "scanned": 1, "changed": 1},
            digest_hash="stub-notion-digest",
            generated_at="2026-06-08T12:30:00+00:00",
            uris=["https://notion.so/roadmap"],
        )


class NotionBackgroundApp(BackgroundWorkerApp[NotionBackgroundWorker, NotionCycleResult]):
    AUTH_FAILURE_THRESHOLD = 2

    def __init__(self) -> None:
        super().__init__("notion", logger_name="notion.background")

    def build_worker(self) -> NotionBackgroundWorker:
        if os.getenv("APP_STORE_USE_TEST_STUBS") == "1":
            return _StubNotionBackgroundWorker()  # type: ignore[return-value]
        return NotionBackgroundWorker()

    def verify_worker(self, worker: NotionBackgroundWorker) -> tuple[bool, str]:
        return worker.verify()

    def reset_for_test(self) -> None:
        worker = self._worker
        if worker is not None:
            close = getattr(worker, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    self.logger.exception("Failed to close Notion background worker")
        super().reset_for_test()
        self.reset_auth_failures()

    def cleanup(self) -> None:
        self.reset_for_test()

    def _execute_cycle(self, ctx: object) -> None:
        worker = self.get_worker()
        try:
            result = self._run_cycle_with_optional_foreground(ctx, worker)
            self.handle_cycle_result(ctx, result)
        except Exception as exc:
            self._error_reporter.report_background_exception(ctx, exc, phase="background_cycle")

    def _run_cycle_with_optional_foreground(self, ctx: object, worker: NotionBackgroundWorker) -> NotionCycleResult:
        if not _should_use_foreground_tools(ctx, worker):
            return self.run_cycle(worker)
        loop = asyncio.new_event_loop()
        previous_client = getattr(worker, "client", None)
        previous_owns_client = getattr(worker, "_owns_client", None)
        conn = None
        try:
            asyncio.set_event_loop(loop)
            conn = loop.run_until_complete(ctx.connect_foreground(lease_duration_seconds=180))  # type: ignore[attr-defined]
            worker.client = _ForegroundToolClient(loop, conn)  # type: ignore[assignment]
            worker._owns_client = False
            return self.run_cycle(worker)
        finally:
            worker.client = previous_client
            if previous_owns_client is not None:
                worker._owns_client = previous_owns_client
            if conn is not None:
                loop.run_until_complete(conn.close())
            asyncio.set_event_loop(None)
            loop.close()

    def run_cycle(self, worker: NotionBackgroundWorker) -> NotionCycleResult:
        try:
            result = worker.run_cycle()
            priority = _PRIORITY_DEFAULT if int(result.stats.get("changed", 0) or 0) > 0 else _PRIORITY_LOW
            return NotionCycleResult(
                summary=result.summary,
                priority=priority,
                digest_hash=result.digest_hash,
                stats=dict(result.stats),
                uris=list(result.uris),
            )
        except AppAuthError as exc:
            return NotionCycleResult(auth_error=str(exc))
        except AppRuntimeFailure as exc:
            message = str(exc)
            if any(marker in message.lower() for marker in ("unauthorized", "forbidden", "http 401", "http 403")):
                return NotionCycleResult(auth_error=message)
            return NotionCycleResult(error=message)
        except Exception as exc:
            return NotionCycleResult(error=str(exc))

    def handle_cycle_result(self, ctx: object, result: NotionCycleResult) -> None:
        if result.auth_error:
            self.report_auth_failure(ctx, result.auth_error)
            return
        self.reset_auth_failures()
        if result.error:
            self.logger.error("Notion background cycle failed: %s", result.error)
            return
        if result.summary:
            self.submit_text(ctx, content=result.summary, priority=result.priority, uris=result.uris)
        else:
            self.logger.info("Notion background cycle unchanged; skipping submit_context")


app = NotionBackgroundApp()


atexit.register(app.cleanup)


def _should_use_foreground_tools(ctx: object, worker: object) -> bool:
    raw = os.getenv("APP_STORE_BG_USE_FOREGROUND_TOOLS", "1").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if getattr(worker, "client", None) is not None:
        return False
    return callable(getattr(ctx, "connect_foreground", None))


def _plain_mcp_value(value: Any) -> Any:
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return value.model_dump(by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        return {str(key): _plain_mcp_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_mcp_value(item) for item in value]
    return value


class _ForegroundToolClient:
    def __init__(self, loop: asyncio.AbstractEventLoop, conn: Any) -> None:
        self._loop = loop
        self._conn = conn

    def list_tools(self) -> list[dict[str, Any]]:
        tools = self._loop.run_until_complete(self._conn.list_tools())
        out: list[dict[str, Any]] = []
        for tool in tools:
            plain = _plain_mcp_value(tool)
            if isinstance(plain, dict):
                out.append(plain)
        return out

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._loop.run_until_complete(self._conn.call_tool(name, **dict(arguments or {})))
        return _plain_mcp_value(result)

    def close(self) -> None:
        return None


if __name__ == "__main__":
    app.main()
