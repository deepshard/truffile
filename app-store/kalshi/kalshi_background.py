from __future__ import annotations

import atexit
import asyncio
import threading
from typing import Any



from truffile.app_runtime import BackgroundWorkerApp
from truffle.app.background_pb2 import BackgroundContext

from auth import KalshiAuthProvider
from bg_worker import BackgroundDigest, KalshiBackgroundWorker
from client import KalshiClient
from config import KalshiConfig

_PRIORITY_DEFAULT = getattr(BackgroundContext, "PRIORITY_DEFAULT", getattr(BackgroundContext, "PRIORITY_HIGH", 1))


class KalshiBackgroundApp(BackgroundWorkerApp[KalshiBackgroundWorker, BackgroundDigest]):
    def __init__(self) -> None:
        super().__init__("kalshi", logger_name="kalshi.background")
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

    def build_worker(self) -> KalshiBackgroundWorker:
        config = KalshiConfig.from_env()
        if not config.api_key:
            raise ValueError("Missing KALSHI_API_KEY")
        if not config.private_key_pem:
            raise ValueError("Missing KALSHI_PRIVATE_KEY")

        auth = KalshiAuthProvider(config.api_key, config.private_key_pem)
        client = KalshiClient(base_url=config.base_url, auth=auth)
        return KalshiBackgroundWorker(client=client, config=config)

    def verify_worker(self, worker: KalshiBackgroundWorker) -> tuple[bool, str]:
        return self._run(worker.verify())

    def run_cycle(self, worker: KalshiBackgroundWorker) -> BackgroundDigest:
        return self._run(worker.run_cycle())

    def handle_cycle_result(self, ctx: Any, result: BackgroundDigest) -> None:
        if result.error:
            self.logger.error("Kalshi background cycle failed", extra={"error": result.error})
            if result.error == "auth_failure":
                self.report_auth_failure(ctx, "kalshi API returned auth error")
            return

        self.reset_auth_failures()
        if result.portfolio_summary:
            self.submit_text(ctx, content=result.portfolio_summary, priority=BackgroundContext.PRIORITY_LOW)

        for alert in result.price_alerts:
            content = (
                f"Price alert: {alert['title']} ({alert['ticker']}) moved "
                f"{alert['direction']} {abs(alert['change'])}c "
                f"(was {alert['previous_price']}c, now {alert['current_price']}c)"
            )
            self.submit_text(
                ctx, content=content, priority=BackgroundContext.PRIORITY_HIGH,
                uris=[f"https://kalshi.com/markets/{alert['ticker']}"],
            )

        for alert in result.settlement_alerts:
            content = (
                f"Market settled: {alert['ticker']} — {alert['result']} "
                f"(${alert['revenue_dollars']})"
            )
            self.submit_text(
                ctx, content=content, priority=BackgroundContext.PRIORITY_HIGH,
                uris=[f"https://kalshi.com/markets/{alert['ticker']}"],
            )

        for update in result.order_updates:
            self.submit_text(
                ctx,
                content=f"Order {update['order_id']}: {update['change']}",
                priority=_PRIORITY_DEFAULT,
            )

        for item in result.feed_items:
            top = item.get("top_markets", [])
            top_str = ", ".join(
                f"{market['title']} ({market.get('yes_bid', '?')}¢)" for market in top[:2]
            )
            content = (
                f"Kalshi [{', '.join(item.get('categories', []))}]: "
                f"{item['title']} — "
                f"{item['total_volume']:,} vol, "
                f"{item['market_count']} markets"
            )
            if top_str:
                content += f" — {top_str}"
            self.submit_text(
                ctx, content=content, priority=BackgroundContext.PRIORITY_LOW,
                uris=[f"https://kalshi.com/events/{item['event_ticker']}"],
            )

    def reset_for_test(self) -> None:
        super().reset_for_test()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()
        self._loop = None

    def cleanup(self) -> None:
        worker = getattr(self, "_worker", None)
        if worker is not None:
            try:
                self._run(worker.close())
            except Exception:
                self.logger.exception("Failed to close Kalshi background worker")
        self.reset_for_test()


app = KalshiBackgroundApp()


if __name__ == "__main__":
    atexit.register(app.cleanup)
    app.main()
