#!/usr/bin/env python3
"""Kalshi MCP server (streamable HTTP) for foreground Truffle app."""

from __future__ import annotations

import atexit
import asyncio
import logging
from typing import Any

import httpx
from app_runtime.mcp import create_mcp_server, run_mcp_server

from client import KalshiClient
from config import (
    KALSHI_API_KEY,
    KALSHI_BASE_URL,
    KALSHI_PRIVATE_KEY,
    normalize_private_key,
)

logger = logging.getLogger("kalshi.foreground")
logger.setLevel(logging.INFO)

mcp = create_mcp_server("kalshi")

_api: KalshiClient | None = None
_watched_tickers: set[str] = set()


def _error(message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "error", "message": message}
    payload.update(extra)
    return payload


def _success(message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "success", "message": message}
    payload.update(extra)
    return payload


async def _report_auth_failure(description: str) -> None:
    from app_runtime import AppRuntimeErrorType, report_app_error

    await report_app_error(
        error_message=f"Kalshi authentication failure: {description}",
        error_type=AppRuntimeErrorType.APP_ERROR_AUTH,
        needs_intervention=True,
        is_fatal=False,
    )


def _validate_range(name: str, value: int | None, min_value: int, max_value: int) -> None:
    if value is None:
        return
    if value < min_value or value > max_value:
        raise ValueError(f"{name} must be between {min_value} and {max_value}")


def _get_api() -> KalshiClient:
    global _api
    if _api is not None:
        return _api

    if not KALSHI_API_KEY:
        raise ValueError("Missing KALSHI_API_KEY")
    if not KALSHI_PRIVATE_KEY:
        raise ValueError("Missing KALSHI_PRIVATE_KEY")

    _api = KalshiClient(
        api_key=KALSHI_API_KEY,
        private_key_pem=normalize_private_key(KALSHI_PRIVATE_KEY),
        base_url=KALSHI_BASE_URL,
    )
    return _api


async def _handle_api_error(error: httpx.HTTPStatusError) -> dict[str, Any]:
    status = error.response.status_code
    if status in {401, 403}:
        try:
            await _report_auth_failure(f"Kalshi API returned {status}")
        except Exception:
            logger.exception("Failed to report Kalshi auth failure")
    response_text = ""
    try:
        response_text = error.response.text
    except Exception:
        response_text = ""
    return _error(
        f"Kalshi API error: {status}",
        response=response_text[:1500],
    )


async def _validate_order(
    *,
    ticker: str,
    side: str,
    action: str,
    count: int,
    price: int | None,
) -> dict[str, Any]:
    api = _get_api()
    errors: list[str] = []
    warnings: list[str] = []
    estimated_cost = 0
    current_balance = 0

    market_resp = await api.get_market(ticker)
    market = market_resp.get("market") or {}
    market_status = str(market.get("status", "unknown")).lower()
    # Kalshi market data can surface tradable markets as "active".
    # Keep strict blocks for clearly non-tradable statuses, and let create_order
    # API decide for ambiguous/unknown status values.
    if market_status in {"closed", "settled", "paused", "unopened"}:
        errors.append(f"Market {ticker} is {market.get('status')}, not open for trading")
    elif market_status not in {"open", "active"}:
        warnings.append(
            f"Market {ticker} has unrecognized status '{market.get('status')}'. "
            "Proceeding to API submission for final tradability check."
        )

    if side == "yes":
        current_price = market.get("yes_ask") if action == "buy" else market.get("yes_bid")
    else:
        current_price = market.get("no_ask") if action == "buy" else market.get("no_bid")

    if price is not None and current_price is not None:
        diff = abs(int(price) - int(current_price))
        if diff > 20:
            warnings.append(
                f"Provided price ({price}c) is {diff}c away from market ({current_price}c)"
            )

    balance_resp = await api.get_balance()
    current_balance = int(balance_resp.get("balance") or 0)

    if action == "buy":
        effective_price = int(price if price is not None else (current_price or 50))
        estimated_cost = count * effective_price
        if estimated_cost > current_balance:
            errors.append(
                f"Insufficient balance: need {estimated_cost}c, have {current_balance}c"
            )

    if count <= 0:
        errors.append("Order quantity must be positive")
    if count > 1000:
        warnings.append("Large order size may have poor execution")

    if price is not None and (price < 1 or price > 99):
        errors.append("Price must be between 1 and 99 cents")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "estimated_cost": estimated_cost,
        "current_balance": current_balance,
        "market_status": market.get("status"),
        "market_open_time": market.get("open_time"),
        "market_close_time": market.get("close_time"),
    }


@mcp.tool(
    "get_markets",
    description=(
        "Search and list Kalshi prediction markets. "
        "Parameters: limit (int, max 1000), cursor (str, pagination), event_ticker (str, filter by event), "
        "series_ticker (str, filter by series), status (str: unopened|open|paused|closed|settled), "
        "tickers (str, comma-separated). "
        "Returns: JSON with fields: markets, count, cursor. "
        "IMPORTANT: use cursor for pagination over large result sets. "
        "Example: get_markets(status='open', limit=20)."
    ),
)
async def get_markets(
    limit: int | None = None,
    cursor: str | None = None,
    event_ticker: str | None = None,
    series_ticker: str | None = None,
    status: str | None = None,
    tickers: str | None = None,
) -> dict[str, Any]:
    """List and search Kalshi prediction markets."""
    try:
        _validate_range("limit", limit, 1, 1000)
        if status and status not in {"unopened", "open", "paused", "closed", "settled"}:
            return _error("status must be one of unopened|open|paused|closed|settled")

        api = _get_api()
        data = await api.get_markets(
            limit=limit,
            cursor=cursor,
            event_ticker=event_ticker,
            series_ticker=series_ticker,
            status=status,
            tickers=tickers,
        )
        markets = data.get("markets", [])
        return _success("Markets fetched", markets=markets, count=len(markets), cursor=data.get("cursor"))
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "get_market",
    description=(
        "Get full details for a single market by ticker. "
        "Parameters: ticker (str, required). "
        "Returns: JSON with fields: market (ticker, title, yes_bid, yes_ask, no_bid, no_ask, volume, open_interest, status). "
        "IMPORTANT: pass exact market ticker. "
        "Example: get_market(ticker='PRES-2028-DEM')."
    ),
)
async def get_market(ticker: str) -> dict[str, Any]:
    """Get details for a specific market ticker."""
    try:
        api = _get_api()
        data = await api.get_market(ticker)
        market = data.get("market")
        if not market:
            return _error(f"Market not found: {ticker}")
        return _success("Market fetched", market=market)
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "get_orderbook",
    description=(
        "Get the orderbook (bid/ask levels) for a market. "
        "Parameters: ticker (str, required), depth (int, default None, max 100). "
        "Returns: JSON with fields: yes_bids, no_bids, summary. "
        "IMPORTANT: use small depth for faster responses. "
        "Example: get_orderbook(ticker='PRES-2028-DEM', depth=10)."
    ),
)
async def get_orderbook(ticker: str, depth: int | None = None) -> dict[str, Any]:
    """Get orderbook levels for a market."""
    try:
        _validate_range("depth", depth, 1, 100)
        api = _get_api()
        data = await api.get_market_orderbook(ticker, depth=depth)
        orderbook = data.get("orderbook")
        if not orderbook:
            return _error(f"Orderbook not found: {ticker}")
        yes_bids = orderbook.get("yes_dollars") or []
        no_bids = orderbook.get("no_dollars") or []
        return _success(
            "Orderbook fetched",
            ticker=ticker,
            yes_bids=[{"price_dollars": x[0], "quantity": x[1]} for x in yes_bids],
            no_bids=[{"price_dollars": x[0], "quantity": x[1]} for x in no_bids],
            summary={
                "yes_levels": len(yes_bids),
                "no_levels": len(no_bids),
                "best_yes_bid": yes_bids[-1][0] if yes_bids else None,
                "best_no_bid": no_bids[-1][0] if no_bids else None,
            },
        )
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "get_trades",
    description=(
        "Get recent public trades for a market or globally. "
        "Parameters: ticker (str), limit (int, max 1000), cursor (str), min_ts (int), max_ts (int). "
        "Returns: JSON with fields: trades, count, cursor. "
        "IMPORTANT: combine ticker + time filters for focused analysis. "
        "Example: get_trades(ticker='PRES-2028-DEM', limit=50)."
    ),
)
async def get_trades(
    ticker: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
    min_ts: int | None = None,
    max_ts: int | None = None,
) -> dict[str, Any]:
    """Get recent trades across markets or for a specific ticker."""
    try:
        _validate_range("limit", limit, 1, 1000)
        api = _get_api()
        data = await api.get_trades(
            ticker=ticker,
            limit=limit,
            cursor=cursor,
            min_ts=min_ts,
            max_ts=max_ts,
        )
        trades = data.get("trades", [])
        return _success("Trades fetched", trades=trades, count=len(trades), cursor=data.get("cursor"))
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "get_events",
    description=(
        "List Kalshi events (each event can contain multiple markets). "
        "Parameters: limit (int, max 200), cursor (str), status (str: open|closed|settled), "
        "series_ticker (str), with_nested_markets (bool). "
        "Returns: JSON with fields: events, count, cursor. "
        "IMPORTANT: set with_nested_markets=true to include markets inline. "
        "Example: get_events(status='open', with_nested_markets=True)."
    ),
)
async def get_events(
    limit: int | None = None,
    cursor: str | None = None,
    status: str | None = None,
    series_ticker: str | None = None,
    with_nested_markets: bool | None = None,
) -> dict[str, Any]:
    """List Kalshi events."""
    try:
        _validate_range("limit", limit, 1, 200)
        if status and status not in {"open", "closed", "settled"}:
            return _error("status must be one of open|closed|settled")

        api = _get_api()
        data = await api.get_events(
            limit=limit,
            cursor=cursor,
            status=status,
            series_ticker=series_ticker,
            with_nested_markets=with_nested_markets,
        )
        events = data.get("events", [])
        return _success("Events fetched", events=events, count=len(events), cursor=data.get("cursor"))
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "get_event",
    description=(
        "Get details for a single event with optional nested markets. "
        "Parameters: event_ticker (str, required), with_nested_markets (bool, default None). "
        "Returns: JSON with fields: event, markets, markets_count. "
        "IMPORTANT: use event ticker, not market ticker. "
        "Example: get_event(event_ticker='FED-RATE-25MAR', with_nested_markets=True)."
    ),
)
async def get_event(event_ticker: str, with_nested_markets: bool | None = None) -> dict[str, Any]:
    """Get detailed info for a specific event ticker."""
    try:
        api = _get_api()
        data = await api.get_event(event_ticker, with_nested_markets=with_nested_markets)
        event = data.get("event")
        if not event:
            return _error(f"Event not found: {event_ticker}")
        markets = data.get("markets") or []
        return _success("Event fetched", event=event, markets=markets, markets_count=len(markets))
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "get_balance",
    description=(
        "Get account cash balance and portfolio value. "
        "Parameters: none. "
        "Returns: JSON with fields: balance_cents, balance_dollars, portfolio_value_cents, portfolio_value_dollars. "
        "IMPORTANT: values are cents from API and dollars as formatted strings. "
        "Example: get_balance()."
    ),
)
async def get_balance() -> dict[str, Any]:
    """Get account balance and portfolio value."""
    try:
        api = _get_api()
        data = await api.get_balance()
        balance = int(data.get("balance") or 0)
        portfolio_value = int(data.get("portfolio_value") or 0)
        return _success(
            "Balance fetched",
            balance_cents=balance,
            portfolio_value_cents=portfolio_value,
            balance_dollars=f"{balance / 100:.2f}",
            portfolio_value_dollars=f"{portfolio_value / 100:.2f}",
        )
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "get_positions",
    description=(
        "Get current open positions. "
        "Parameters: limit (int, max 100), cursor (str), ticker (str), event_ticker (str), "
        "count_filter (str: position|total_traded). "
        "Returns: JSON with fields: positions, summary, cursor. "
        "IMPORTANT: summary.total_positions counts only non-zero positions. "
        "Example: get_positions(limit=50)."
    ),
)
async def get_positions(
    limit: int | None = None,
    cursor: str | None = None,
    ticker: str | None = None,
    event_ticker: str | None = None,
    count_filter: str | None = None,
) -> dict[str, Any]:
    """Get current positions."""
    try:
        _validate_range("limit", limit, 1, 100)
        if count_filter and count_filter not in {"position", "total_traded"}:
            return _error("count_filter must be one of position|total_traded")

        api = _get_api()
        data = await api.get_positions(
            limit=limit,
            cursor=cursor,
            ticker=ticker,
            event_ticker=event_ticker,
            count_filter=count_filter,
        )
        positions = data.get("market_positions", [])
        total_positions = len([p for p in positions if int(p.get("position", 0)) != 0])
        return _success(
            "Positions fetched",
            positions=positions,
            summary={"total_positions": total_positions, "total_returned": len(positions)},
            cursor=data.get("cursor"),
        )
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "get_orders",
    description=(
        "Get order history or active resting orders. "
        "Parameters: ticker (str), event_ticker (str), status (str: resting|canceled|executed), "
        "limit (int, max 200), cursor (str), min_ts/max_ts (int). "
        "Returns: JSON with fields: orders, summary, cursor. "
        "IMPORTANT: use status='resting' to monitor currently open orders. "
        "Example: get_orders(status='resting')."
    ),
)
async def get_orders(
    ticker: str | None = None,
    event_ticker: str | None = None,
    status: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
    min_ts: int | None = None,
    max_ts: int | None = None,
) -> dict[str, Any]:
    """Get order history and active orders."""
    try:
        _validate_range("limit", limit, 1, 200)
        if status and status not in {"resting", "canceled", "executed"}:
            return _error("status must be one of resting|canceled|executed")

        api = _get_api()
        data = await api.get_orders(
            ticker=ticker,
            event_ticker=event_ticker,
            status=status,
            limit=limit,
            cursor=cursor,
            min_ts=min_ts,
            max_ts=max_ts,
        )
        orders = data.get("orders", [])
        return _success(
            "Orders fetched",
            orders=orders,
            summary={
                "total": len(orders),
                "resting": len([o for o in orders if o.get("status") == "resting"]),
                "executed": len([o for o in orders if o.get("status") == "executed"]),
            },
            cursor=data.get("cursor"),
        )
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "create_order",
    description=(
        "Place a new order on Kalshi (executes a real trade). "
        "Parameters: ticker (str), side (yes|no), action (buy|sell), count (int), type (limit|market, default limit), "
        "yes_price/no_price (int, cents 1-99), client_order_id (str), expiration_ts (int). "
        "Returns: JSON with fields: order, warnings. "
        "IMPORTANT: this tool pre-validates market status and available balance before submission. "
        "Example: create_order(ticker='PRES-2028-DEM', side='yes', action='buy', count=10, type='limit', yes_price=55)."
    ),
)
async def create_order(
    ticker: str,
    side: str,
    action: str,
    count: int,
    type: str = "limit",
    yes_price: int | None = None,
    no_price: int | None = None,
    client_order_id: str | None = None,
    expiration_ts: int | None = None,
) -> dict[str, Any]:
    """Place a new order on Kalshi."""
    try:
        if side not in {"yes", "no"}:
            return _error("side must be yes or no")
        if action not in {"buy", "sell"}:
            return _error("action must be buy or sell")
        if type not in {"limit", "market"}:
            return _error("type must be limit or market")

        # Keep price inputs aligned to side to avoid ambiguous/invalid payloads.
        if side == "yes" and no_price is not None:
            return _error("For side='yes', provide yes_price only")
        if side == "no" and yes_price is not None:
            return _error("For side='no', provide no_price only")
        if type == "limit":
            if side == "yes" and yes_price is None:
                return _error("For limit yes orders, provide yes_price")
            if side == "no" and no_price is None:
                return _error("For limit no orders, provide no_price")

        selected_price = yes_price if side == "yes" else no_price
        validation = await _validate_order(
            ticker=ticker,
            side=side,
            action=action,
            count=count,
            price=selected_price,
        )
        if not validation["valid"]:
            return _error(
                "Order validation failed",
                errors=validation["errors"],
                warnings=validation["warnings"],
                estimated_cost=validation["estimated_cost"],
                current_balance=validation["current_balance"],
            )

        payload = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "type": type,
            "yes_price": yes_price,
            "no_price": no_price,
            "client_order_id": client_order_id,
            "expiration_ts": expiration_ts,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        api = _get_api()
        data = await api.create_order(payload)
        order = data.get("order")
        if not order:
            return _error("Order created but no order details were returned")

        return _success(
            "Order created successfully",
            order=order,
            warnings=validation["warnings"],
        )
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "cancel_order",
    description=(
        "Cancel a single resting order. "
        "Parameters: order_id (str, required). "
        "Returns: JSON with fields: order. "
        "IMPORTANT: order must still be cancelable (resting). "
        "Example: cancel_order(order_id='abc-123-def')."
    ),
)
async def cancel_order(order_id: str) -> dict[str, Any]:
    """Cancel a resting order by order ID."""
    try:
        api = _get_api()
        data = await api.cancel_order(order_id)
        order = data.get("order")
        if not order:
            return _error(f"Order {order_id} canceled but no order details were returned")
        return _success("Order canceled successfully", order=order)
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "batch_cancel_orders",
    description=(
        "Cancel up to 20 orders in one request. "
        "Parameters: order_ids (array of strings, required, max 20). "
        "Returns: JSON with fields: cancelled_count, requested_count, cancelled_orders. "
        "IMPORTANT: include only currently resting orders for best results. "
        "Example: batch_cancel_orders(order_ids=['id1','id2'])."
    ),
)
async def batch_cancel_orders(order_ids: list[str]) -> dict[str, Any]:
    """Cancel up to 20 orders in one request."""
    try:
        if not order_ids:
            return _error("order_ids must contain at least one order ID")
        if len(order_ids) > 20:
            return _error("order_ids cannot exceed 20")

        api = _get_api()
        data = await api.batch_cancel_orders(order_ids)
        orders = data.get("orders", [])
        return _success(
            "Batch cancel executed",
            cancelled_count=len(orders),
            requested_count=len(order_ids),
            cancelled_orders=orders,
        )
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "get_fills",
    description=(
        "Get fill history (executed trades on your orders). "
        "Parameters: ticker (str), order_id (str), limit (int, max 200), cursor (str), min_ts/max_ts (int). "
        "Returns: JSON with fields: fills, summary, cursor. "
        "IMPORTANT: summary includes total volume and buy/sell counts. "
        "Example: get_fills(ticker='PRES-2028-DEM', limit=20)."
    ),
)
async def get_fills(
    ticker: str | None = None,
    order_id: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
    min_ts: int | None = None,
    max_ts: int | None = None,
) -> dict[str, Any]:
    """Get fill history (executed trades)."""
    try:
        _validate_range("limit", limit, 1, 200)
        api = _get_api()
        data = await api.get_fills(
            ticker=ticker,
            order_id=order_id,
            limit=limit,
            cursor=cursor,
            min_ts=min_ts,
            max_ts=max_ts,
        )
        fills = data.get("fills", [])
        return _success(
            "Fills fetched",
            fills=fills,
            summary={
                "total": len(fills),
                "total_volume": sum(int(f.get("count") or 0) for f in fills),
                "buys": len([f for f in fills if f.get("action") == "buy"]),
                "sells": len([f for f in fills if f.get("action") == "sell"]),
            },
            cursor=data.get("cursor"),
        )
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "get_settlements",
    description=(
        "Get settlement history for resolved markets. "
        "Parameters: ticker (str), event_ticker (str), limit (int, max 200), cursor (str), min_ts/max_ts (int). "
        "Returns: JSON with fields: settlements, summary, cursor. "
        "IMPORTANT: summary includes aggregate realized revenue. "
        "Example: get_settlements(limit=20)."
    ),
)
async def get_settlements(
    ticker: str | None = None,
    event_ticker: str | None = None,
    limit: int | None = None,
    cursor: str | None = None,
    min_ts: int | None = None,
    max_ts: int | None = None,
) -> dict[str, Any]:
    """Get settlement history."""
    try:
        _validate_range("limit", limit, 1, 200)
        api = _get_api()
        data = await api.get_settlements(
            ticker=ticker,
            event_ticker=event_ticker,
            limit=limit,
            cursor=cursor,
            min_ts=min_ts,
            max_ts=max_ts,
        )
        settlements = data.get("settlements", [])
        total_revenue = sum(int(s.get("revenue") or 0) for s in settlements)
        return _success(
            "Settlements fetched",
            settlements=settlements,
            summary={
                "total": len(settlements),
                "total_revenue_cents": total_revenue,
                "total_revenue_dollars": f"{total_revenue / 100:.2f}",
                "profitable_settlements": len([s for s in settlements if int(s.get("revenue") or 0) > 0]),
            },
            cursor=data.get("cursor"),
        )
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "get_portfolio_summary",
    description=(
        "Get a complete portfolio overview in one call. "
        "Parameters: none. "
        "Returns: JSON with fields: balance_cents, balance_dollars, portfolio_value_cents, portfolio_value_dollars, positions, total_positions. "
        "IMPORTANT: enriches positions with current market info when available. "
        "Example: get_portfolio_summary()."
    ),
)
async def get_portfolio_summary() -> dict[str, Any]:
    try:
        api = _get_api()
        balance_data = await api.get_balance()
        positions_data = await api.get_positions(limit=100)
        positions = positions_data.get("market_positions", [])

        enriched = []
        for pos in positions:
            count = int(pos.get("position", 0))
            if count == 0:
                continue
            ticker = pos.get("ticker", "")
            market_info = {}
            try:
                market_resp = await api.get_market(ticker)
                market_info = market_resp.get("market", {})
            except Exception:
                pass
            enriched.append(
                {
                    "ticker": ticker,
                    "title": market_info.get("title", ""),
                    "side": "yes" if count > 0 else "no",
                    "count": abs(count),
                    "yes_price": market_info.get("yes_bid"),
                    "no_price": market_info.get("no_bid"),
                    "status": market_info.get("status", "unknown"),
                }
            )

        balance = int(balance_data.get("balance", 0))
        portfolio_value = int(balance_data.get("portfolio_value", 0))
        return _success(
            f"Portfolio: ${balance/100:.2f} cash, ${portfolio_value/100:.2f} portfolio value, {len(enriched)} open positions",
            balance_cents=balance,
            balance_dollars=f"{balance/100:.2f}",
            portfolio_value_cents=portfolio_value,
            portfolio_value_dollars=f"{portfolio_value/100:.2f}",
            positions=enriched,
            total_positions=len(enriched),
        )
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error))


@mcp.tool(
    "watchlist_manage",
    description=(
        "Manage foreground watchlist metadata for Kalshi tickers. "
        "Parameters: action (list|add|remove|clear), tickers (array for add/remove). "
        "Returns: JSON with fields: watched_tickers. "
        "IMPORTANT: foreground and background run in separate processes; background monitoring is based on its own state and active positions. "
        "Example: watchlist_manage(action='add', tickers=['PRES-2028-DEM'])."
    ),
)
async def watchlist_manage(action: str, tickers: list[str] | None = None) -> dict[str, Any]:
    global _watched_tickers
    normalized_action = action.strip().lower()

    if normalized_action == "list":
        return _success(
            f"Watching {len(_watched_tickers)} tickers",
            watched_tickers=sorted(_watched_tickers),
        )

    if normalized_action == "add":
        if not tickers:
            return _error("tickers list required for add")
        for ticker in tickers:
            cleaned = ticker.strip().upper()
            if cleaned:
                _watched_tickers.add(cleaned)
        return _success(
            f"Added {len(tickers)} tickers, now watching {len(_watched_tickers)}",
            watched_tickers=sorted(_watched_tickers),
        )

    if normalized_action == "remove":
        if not tickers:
            return _error("tickers list required for remove")
        for ticker in tickers:
            cleaned = ticker.strip().upper()
            if cleaned:
                _watched_tickers.discard(cleaned)
        return _success(
            f"Removed tickers, now watching {len(_watched_tickers)}",
            watched_tickers=sorted(_watched_tickers),
        )

    if normalized_action == "clear":
        _watched_tickers.clear()
        return _success("Watchlist cleared", watched_tickers=[])

    return _error(f"Unknown action: {action}. Use list, add, remove, or clear.")


@mcp.tool(
    "kalshi_health",
    description=(
        "Check health of Kalshi API connection and credentials. "
        "Parameters: none. "
        "Returns: JSON with fields: api_healthy, balance_cents, balance_dollars (when healthy). "
        "IMPORTANT: auth failures are reported to runtime as APP_ERROR_AUTH. "
        "Example: kalshi_health()."
    ),
)
async def kalshi_health() -> dict[str, Any]:
    try:
        api = _get_api()
        data = await api.get_balance()
        balance = int(data.get("balance", 0))
        return _success(
            "Kalshi API healthy",
            api_healthy=True,
            balance_cents=balance,
            balance_dollars=f"{balance / 100:.2f}",
        )
    except httpx.HTTPStatusError as error:
        return await _handle_api_error(error)
    except Exception as error:
        return _error(str(error), api_healthy=False)


def _cleanup() -> None:
    global _api
    if _api is None:
        return
    try:
        asyncio.run(_api.close())
    except Exception:
        pass
    _api = None


def main() -> None:
    atexit.register(_cleanup)
    run_mcp_server(mcp, logger)


if __name__ == "__main__":
    main()
