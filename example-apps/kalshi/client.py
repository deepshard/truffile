#!/usr/bin/env python3
"""Async Kalshi API client using API key + RSA-PSS authentication."""

from __future__ import annotations

import base64
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class KalshiClient:
    """Minimal async client for Kalshi REST endpoints used by the MCP tools."""

    def __init__(
        self,
        api_key: str,
        private_key_pem: str,
        base_url: str,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=None,
        )
        self._http = httpx.AsyncClient(timeout=timeout)

    def _build_auth_headers(self, method: str, path: str) -> Dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        message = f"{timestamp}{method.upper()}{path}".encode("utf-8")

        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=hashes.SHA256().digest_size,
            ),
            hashes.SHA256(),
        )
        signature_b64 = base64.b64encode(signature).decode("utf-8")

        return {
            "KALSHI-ACCESS-KEY": self._api_key,
            "KALSHI-ACCESS-SIGNATURE": signature_b64,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self._base_url}{path}"
        parsed = urlparse(url)
        headers = self._build_auth_headers(method, parsed.path)
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
            method=method.upper(),
            url=url,
            params=clean_params,
            json=clean_json,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        try:
            await self._http.aclose()
        except Exception:
            pass

    async def get_markets(
        self,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        event_ticker: Optional[str] = None,
        series_ticker: Optional[str] = None,
        status: Optional[str] = None,
        tickers: Optional[str] = None,
    ) -> Dict[str, Any]:
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

    async def get_market(self, ticker: str) -> Dict[str, Any]:
        return await self._request("GET", f"/markets/{ticker}")

    async def get_market_orderbook(
        self,
        ticker: str,
        *,
        depth: Optional[int] = None,
    ) -> Dict[str, Any]:
        return await self._request(
            "GET",
            f"/markets/{ticker}/orderbook",
            params={"depth": depth},
        )

    async def get_trades(
        self,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        ticker: Optional[str] = None,
        min_ts: Optional[int] = None,
        max_ts: Optional[int] = None,
    ) -> Dict[str, Any]:
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
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        with_nested_markets: Optional[bool] = None,
        status: Optional[str] = None,
        series_ticker: Optional[str] = None,
    ) -> Dict[str, Any]:
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
        with_nested_markets: Optional[bool] = None,
    ) -> Dict[str, Any]:
        return await self._request(
            "GET",
            f"/events/{event_ticker}",
            params={"with_nested_markets": with_nested_markets},
        )

    async def get_balance(self) -> Dict[str, Any]:
        return await self._request("GET", "/portfolio/balance")

    async def get_positions(
        self,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        count_filter: Optional[str] = None,
        ticker: Optional[str] = None,
        event_ticker: Optional[str] = None,
    ) -> Dict[str, Any]:
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
        ticker: Optional[str] = None,
        event_ticker: Optional[str] = None,
        min_ts: Optional[int] = None,
        max_ts: Optional[int] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
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

    async def create_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/portfolio/orders", json_body=payload)

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return await self._request("DELETE", f"/portfolio/orders/{order_id}")

    async def batch_cancel_orders(self, order_ids: list[str]) -> Dict[str, Any]:
        return await self._request(
            "DELETE",
            "/portfolio/orders/batched",
            json_body={"ids": order_ids},
        )

    async def get_fills(
        self,
        *,
        ticker: Optional[str] = None,
        order_id: Optional[str] = None,
        min_ts: Optional[int] = None,
        max_ts: Optional[int] = None,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
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
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        ticker: Optional[str] = None,
        event_ticker: Optional[str] = None,
        min_ts: Optional[int] = None,
        max_ts: Optional[int] = None,
    ) -> Dict[str, Any]:
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
