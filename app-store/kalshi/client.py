"""Async Kalshi API client with injectable auth and HTTP transport."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from truffile.app_runtime import ApiKeyProvider, HttpTransport


class _HttpxTransport:
    def __init__(self, *, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        return await self._client.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json,
            headers=headers,
            content=content,
        )

    async def close(self) -> None:
        await self._client.aclose()


class KalshiClient:
    def __init__(
        self,
        *,
        base_url: str,
        auth: ApiKeyProvider,
        http: HttpTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._http = http or _HttpxTransport()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = self._auth.get_auth_headers(method, urlparse(url).path)
        clean_params = (
            {k: v for k, v in params.items() if v is not None}
            if params is not None
            else None
        )
        clean_json = (
            {k: v for k, v in json_body.items() if v is not None}
            if json_body is not None
            else None
        )
        response = await self._http.request(
            method.upper(),
            url,
            params=clean_params,
            json=clean_json,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        try:
            await self._http.close()
        except Exception:
            pass

    async def get_markets(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        status: str | None = None,
        tickers: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/markets",
            params={
                "limit": limit,
                "cursor": cursor,
                "event_ticker": event_ticker,
                "series_ticker": series_ticker,
                "status": status,
                "tickers": tickers,
            },
        )

    async def get_market(self, ticker: str) -> dict[str, Any]:
        return await self._request("GET", f"/markets/{ticker}")

    async def get_market_orderbook(
        self,
        ticker: str,
        *,
        depth: int | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/markets/{ticker}/orderbook",
            params={"depth": depth},
        )

    async def get_trades(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/markets/trades",
            params={
                "limit": limit,
                "cursor": cursor,
                "ticker": ticker,
                "min_ts": min_ts,
                "max_ts": max_ts,
            },
        )

    async def get_events(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        with_nested_markets: bool | None = None,
        status: str | None = None,
        series_ticker: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/events",
            params={
                "limit": limit,
                "cursor": cursor,
                "with_nested_markets": with_nested_markets,
                "status": status,
                "series_ticker": series_ticker,
            },
        )

    async def get_event(
        self,
        event_ticker: str,
        *,
        with_nested_markets: bool | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/events/{event_ticker}",
            params={"with_nested_markets": with_nested_markets},
        )

    async def get_balance(self) -> dict[str, Any]:
        return await self._request("GET", "/portfolio/balance")

    async def get_positions(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = None,
        count_filter: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/portfolio/positions",
            params={
                "cursor": cursor,
                "limit": limit,
                "count_filter": count_filter,
                "ticker": ticker,
                "event_ticker": event_ticker,
            },
        )

    async def get_orders(
        self,
        *,
        ticker: str | None = None,
        event_ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/portfolio/orders",
            params={
                "ticker": ticker,
                "event_ticker": event_ticker,
                "min_ts": min_ts,
                "max_ts": max_ts,
                "status": status,
                "limit": limit,
                "cursor": cursor,
            },
        )

    async def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/portfolio/orders", json_body=payload)

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/portfolio/orders/{order_id}")

    async def batch_cancel_orders(self, order_ids: list[str]) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            "/portfolio/orders/batched",
            json_body={"ids": order_ids},
        )

    async def get_fills(
        self,
        *,
        ticker: str | None = None,
        order_id: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/portfolio/fills",
            params={
                "ticker": ticker,
                "order_id": order_id,
                "min_ts": min_ts,
                "max_ts": max_ts,
                "limit": limit,
                "cursor": cursor,
            },
        )

    async def get_settlements(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        ticker: str | None = None,
        event_ticker: str | None = None,
        min_ts: int | None = None,
        max_ts: int | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/portfolio/settlements",
            params={
                "limit": limit,
                "cursor": cursor,
                "ticker": ticker,
                "event_ticker": event_ticker,
                "min_ts": min_ts,
                "max_ts": max_ts,
            },
        )
