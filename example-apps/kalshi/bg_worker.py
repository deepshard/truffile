from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from client import KalshiClient
from config import (
    CATEGORY_KEYWORDS,
    DEFAULT_WATCHED_TICKERS,
    KALSHI_API_KEY,
    KALSHI_BASE_URL,
    KALSHI_CATEGORIES,
    KALSHI_FEED_URL,
    KALSHI_PRIVATE_KEY,
    normalize_private_key,
)

logger = logging.getLogger("kalshi.bg_worker")

PRICE_CHANGE_THRESHOLD = 10
FEED_ITEMS_PER_CYCLE = 3


@dataclass
class BackgroundDigest:
    generated_at: str
    portfolio_summary: str = ""
    price_alerts: list[dict[str, Any]] = field(default_factory=list)
    settlement_alerts: list[dict[str, Any]] = field(default_factory=list)
    order_updates: list[dict[str, Any]] = field(default_factory=list)
    feed_items: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


class KalshiBackgroundWorker:
    def __init__(self) -> None:
        if not KALSHI_API_KEY or not KALSHI_PRIVATE_KEY:
            raise ValueError("Missing KALSHI_API_KEY or KALSHI_PRIVATE_KEY")

        self.client = KalshiClient(
            api_key=KALSHI_API_KEY,
            private_key_pem=normalize_private_key(KALSHI_PRIVATE_KEY),
            base_url=KALSHI_BASE_URL,
        )

        self._last_prices: dict[str, int] = {}
        self._last_order_ids: set[str] = set()
        self._settled_tickers: set[str] = set()
        self._watched_tickers: set[str] = set(DEFAULT_WATCHED_TICKERS)
        self._is_seeded = False
        self._categories: set[str] = KALSHI_CATEGORIES
        self._seen_feed_events: set[str] = set()
        self._feed_url_tickers: list[str] = self._parse_feed_url(KALSHI_FEED_URL)

    async def close(self) -> None:
        try:
            await self.client.close()
        except Exception:
            pass

    async def verify(self) -> tuple[bool, str]:
        try:
            data = await self.client.get_balance()
            balance = int(data.get("balance", 0))
            return True, f"Kalshi auth OK, balance: {balance}c"
        except httpx.HTTPStatusError as error:
            return False, f"Kalshi API error: {error.response.status_code}"
        except Exception as error:
            return False, f"Kalshi verification failed: {error}"

    async def run_cycle(self) -> BackgroundDigest:
        generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()

        try:
            balance_data = await self.client.get_balance()
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {401, 403}:
                return BackgroundDigest(generated_at=generated_at, error="auth_failure")
            return BackgroundDigest(generated_at=generated_at, error=str(error))
        except Exception as error:
            return BackgroundDigest(generated_at=generated_at, error=str(error))

        balance = int(balance_data.get("balance", 0))
        portfolio_value = int(balance_data.get("portfolio_value", 0))

        try:
            positions_data = await self.client.get_positions(limit=100)
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {401, 403}:
                return BackgroundDigest(generated_at=generated_at, error="auth_failure")
            return BackgroundDigest(generated_at=generated_at, error=str(error))
        except Exception as error:
            return BackgroundDigest(generated_at=generated_at, error=str(error))

        positions = positions_data.get("market_positions", [])
        active_tickers: set[str] = set()
        for position in positions:
            count = int(position.get("position", 0))
            if count != 0:
                ticker = (position.get("ticker") or "").strip().upper()
                if ticker:
                    active_tickers.add(ticker)

        all_watched = self._watched_tickers | active_tickers

        try:
            price_alerts = await self._check_price_changes(all_watched)
            settlement_alerts = await self._check_settlements(active_tickers)
            order_updates = await self._check_order_changes()
            feed_items = await self._fetch_feed_items()
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {401, 403}:
                return BackgroundDigest(generated_at=generated_at, error="auth_failure")
            return BackgroundDigest(generated_at=generated_at, error=str(error))
        except Exception as error:
            return BackgroundDigest(generated_at=generated_at, error=str(error))

        has_activity = balance > 0 or portfolio_value > 0 or active_tickers or all_watched
        portfolio_summary = (
            f"Portfolio: ${balance/100:.2f} cash, ${portfolio_value/100:.2f} value. "
            f"{len(active_tickers)} open positions. "
            f"Watching {len(all_watched)} markets."
        ) if has_activity else ""

        if not self._is_seeded:
            self._is_seeded = True
            return BackgroundDigest(
                generated_at=generated_at,
                portfolio_summary=portfolio_summary,
                feed_items=feed_items,
            )

        return BackgroundDigest(
            generated_at=generated_at,
            portfolio_summary=portfolio_summary,
            price_alerts=price_alerts,
            settlement_alerts=settlement_alerts,
            order_updates=order_updates,
            feed_items=feed_items,
        )

    async def _check_price_changes(self, tickers: set[str]) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for ticker in tickers:
            if not ticker:
                continue
            try:
                data = await self.client.get_market(ticker)
                market = data.get("market", {})
                yes_bid = int(market.get("yes_bid") or 0)
                title = market.get("title", ticker)

                previous = self._last_prices.get(ticker)
                self._last_prices[ticker] = yes_bid

                if previous is not None:
                    diff = yes_bid - previous
                    if abs(diff) >= PRICE_CHANGE_THRESHOLD:
                        alerts.append(
                            {
                                "ticker": ticker,
                                "title": title,
                                "previous_price": previous,
                                "current_price": yes_bid,
                                "change": diff,
                                "direction": "up" if diff > 0 else "down",
                            }
                        )
            except httpx.HTTPStatusError as error:
                if error.response.status_code in {401, 403}:
                    raise
                logger.warning("Failed to check price for %s", ticker, exc_info=True)
            except Exception:
                logger.warning("Failed to check price for %s", ticker, exc_info=True)
        return alerts

    async def _check_settlements(self, active_tickers: set[str]) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        try:
            data = await self.client.get_settlements(limit=20)
            for settlement in data.get("settlements", []):
                ticker = (settlement.get("ticker") or "").strip().upper()
                # Prefer active position settlements, but allow all as fallback context.
                if active_tickers and ticker and ticker not in active_tickers:
                    continue
                key = f"{ticker}:{settlement.get('settled_time', settlement.get('settled_at', ''))}"
                if key in self._settled_tickers:
                    continue
                self._settled_tickers.add(key)

                revenue = int(settlement.get("revenue") or 0)
                alerts.append(
                    {
                        "ticker": ticker,
                        "revenue_cents": revenue,
                        "revenue_dollars": f"{revenue/100:.2f}",
                        "result": "profit" if revenue > 0 else ("loss" if revenue < 0 else "break-even"),
                    }
                )
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {401, 403}:
                raise
            logger.warning("Failed to check settlements", exc_info=True)
        except Exception:
            logger.warning("Failed to check settlements", exc_info=True)
        return alerts

    async def _check_order_changes(self) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        try:
            data = await self.client.get_orders(status="resting", limit=100)
            current_ids = {
                order.get("order_id", "")
                for order in data.get("orders", [])
                if order.get("order_id")
            }

            if self._last_order_ids:
                filled_or_canceled = self._last_order_ids - current_ids
                new_orders = current_ids - self._last_order_ids

                for order_id in filled_or_canceled:
                    alerts.append({"order_id": order_id, "change": "filled_or_canceled"})
                for order_id in new_orders:
                    alerts.append({"order_id": order_id, "change": "new_resting"})

            self._last_order_ids = current_ids
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {401, 403}:
                raise
            logger.warning("Failed to check order changes", exc_info=True)
        except Exception:
            logger.warning("Failed to check order changes", exc_info=True)
        return alerts

    async def _fetch_feed_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        try:
            data = await self.client.get_events(
                status="open", with_nested_markets=True, limit=30,
            )
            events = data.get("events", [])

            candidates: list[dict[str, Any]] = []
            for event in events:
                event_ticker = (event.get("event_ticker") or "").strip()
                if not event_ticker or event_ticker in self._seen_feed_events:
                    continue

                title = event.get("title", "")
                markets = event.get("markets") or []
                total_volume = sum(int(m.get("volume") or 0) for m in markets)

                matched = self._match_categories(title)
                score = total_volume + (1_000_000 if matched else 0)
                tags = sorted(matched | {"trending"})

                candidates.append({
                    "event_ticker": event_ticker,
                    "title": title,
                    "categories": tags,
                    "total_volume": total_volume,
                    "market_count": len(markets),
                    "top_markets": self._format_top_markets(markets),
                    "_score": score,
                })

            candidates.sort(key=lambda e: e["_score"], reverse=True)

            for c in candidates[:FEED_ITEMS_PER_CYCLE]:
                del c["_score"]
                self._seen_feed_events.add(c["event_ticker"])
                items.append(c)
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {401, 403}:
                raise
            logger.warning("Failed to fetch feed items", exc_info=True)
        except Exception:
            logger.warning("Failed to fetch feed items", exc_info=True)

        for ticker in self._feed_url_tickers:
            if ticker in self._seen_feed_events:
                continue
            try:
                data = await self.client.get_event(ticker, with_nested_markets=True)
                event = data.get("event")
                if event:
                    markets = data.get("markets") or []
                    self._seen_feed_events.add(ticker)
                    items.append({
                        "event_ticker": ticker,
                        "title": event.get("title", ticker),
                        "categories": ["followed"],
                        "total_volume": sum(int(m.get("volume") or 0) for m in markets),
                        "market_count": len(markets),
                        "top_markets": self._format_top_markets(markets),
                    })
            except httpx.HTTPStatusError as error:
                if error.response.status_code in {401, 403}:
                    raise
                logger.debug("URL ticker %s not found as event", ticker)
            except Exception:
                logger.debug("URL ticker %s not found as event", ticker)

        if len(self._seen_feed_events) > 500:
            self._seen_feed_events.clear()

        return items

    def _match_categories(self, text: str) -> set[str]:
        matched: set[str] = set()
        text_lower = text.lower()
        for category in self._categories:
            if category == "trending":
                continue
            keywords = CATEGORY_KEYWORDS.get(category, [])
            for keyword in keywords:
                if keyword in text_lower:
                    matched.add(category)
                    break
        return matched

    @staticmethod
    def _format_top_markets(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sorted_markets = sorted(
            markets, key=lambda m: int(m.get("volume") or 0), reverse=True,
        )
        return [
            {
                "ticker": m.get("ticker", ""),
                "title": m.get("title", ""),
                "yes_bid": m.get("yes_bid"),
                "volume": m.get("volume", 0),
            }
            for m in sorted_markets[:3]
        ]

    @staticmethod
    def _parse_feed_url(url: str) -> list[str]:
        if not url:
            return []
        from urllib.parse import urlparse

        path = urlparse(url).path.strip("/")
        parts = [p for p in path.split("/") if p]
        if parts:
            return [parts[-1].upper()]
        return []
