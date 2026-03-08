from __future__ import annotations

import asyncio
import atexit
import logging
import sys

import httpx

from app_runtime.background import BackgroundRunContext, run_background
from truffle.app.background_pb2 import BackgroundContext

from bg_worker import KalshiBackgroundWorker

logger = logging.getLogger("kalshi.background")
logger.setLevel(logging.INFO)

_worker: KalshiBackgroundWorker | None = None
_loop: asyncio.AbstractEventLoop | None = None


def _is_verify_mode() -> bool:
    return bool(sys.argv and len(sys.argv) > 1 and "verify" in sys.argv[1].lower())


def _run(coro):
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop.run_until_complete(coro)


def _ensure_worker() -> KalshiBackgroundWorker:
    global _worker
    if _worker is None:
        _worker = KalshiBackgroundWorker()
    return _worker


async def _report_auth_failure(description: str) -> None:
    from app_runtime import AppRuntimeErrorType, report_app_error

    await report_app_error(
        error_message=f"Kalshi authentication failure: {description}",
        error_type=AppRuntimeErrorType.APP_ERROR_AUTH,
        needs_intervention=True,
        is_fatal=False,
    )


def _submit(ctx: BackgroundRunContext, content: str, priority: int) -> None:
    ctx.bg.submit_context(content=content, uris=[], priority=priority)


def kalshi_ambient(ctx: BackgroundRunContext) -> None:
    worker = _ensure_worker()

    try:
        result = _run(worker.run_cycle())
    except httpx.HTTPStatusError as error:
        logger.exception("Kalshi API error in background cycle")
        if error.response.status_code in {401, 403}:
            try:
                _run(_report_auth_failure(f"API returned {error.response.status_code}"))
            except Exception:
                logger.exception("Failed to report auth failure")
        return
    except Exception:
        logger.exception("Kalshi background cycle crashed")
        return

    if result.error:
        logger.error("Kalshi background cycle failed", extra={"error": result.error})
        if result.error == "auth_failure":
            try:
                _run(_report_auth_failure("API returned 401/403"))
            except Exception:
                logger.exception("Failed to report auth failure")
        return

    if result.portfolio_summary:
        _submit(ctx, result.portfolio_summary, BackgroundContext.PRIORITY_LOW)

    for alert in result.price_alerts:
        content = (
            f"Price alert: {alert['title']} ({alert['ticker']}) moved "
            f"{alert['direction']} {abs(alert['change'])}c "
            f"(was {alert['previous_price']}c, now {alert['current_price']}c)"
        )
        _submit(ctx, content, BackgroundContext.PRIORITY_HIGH)

    for alert in result.settlement_alerts:
        content = (
            f"Market settled: {alert['ticker']} — {alert['result']} "
            f"(${alert['revenue_dollars']})"
        )
        _submit(ctx, content, BackgroundContext.PRIORITY_HIGH)

    for update in result.order_updates:
        content = f"Order {update['order_id']}: {update['change']}"
        _submit(ctx, content, BackgroundContext.PRIORITY_DEFAULT)

    for item in result.feed_items:
        top = item.get("top_markets", [])
        top_str = ", ".join(
            f"{m['title']} ({m.get('yes_bid', '?')}¢)" for m in top[:2]
        )
        content = (
            f"Kalshi [{', '.join(item.get('categories', []))}]: "
            f"{item['title']} — "
            f"{item['total_volume']:,} vol, "
            f"{item['market_count']} markets"
        )
        if top_str:
            content += f" — {top_str}"
        _submit(ctx, content, BackgroundContext.PRIORITY_LOW)


def verify() -> int:
    worker = _ensure_worker()
    ok, message = _run(worker.verify())
    if ok:
        logger.info(message)
        return 0
    logger.error(message)
    return 1


def _cleanup() -> None:
    global _worker
    global _loop

    if _worker is not None:
        try:
            _run(_worker.close())
        except Exception:
            logger.exception("Failed to close Kalshi background worker")
        finally:
            _worker = None

    if _loop is not None and not _loop.is_closed():
        _loop.close()
        _loop = None


if __name__ == "__main__":
    atexit.register(_cleanup)
    if _is_verify_mode():
        sys.exit(verify())
    run_background(kalshi_ambient)
