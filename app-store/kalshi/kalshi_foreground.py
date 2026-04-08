from __future__ import annotations

import atexit
import asyncio
from typing import Any

import httpx



from truffile.app_runtime import ForegroundApp, ToolSpec, err, ok
from truffile.app_runtime.icons import phosphor_icon_url

from auth import KalshiAuthProvider
from client import KalshiClient
from config import KalshiConfig

_client: KalshiClient | None = None
_watched_tickers: set[str] = set()


def set_client(client: KalshiClient | None) -> None:
    global _client
    _client = client


def reset_for_test() -> None:
    global _watched_tickers
    set_client(None)
    _watched_tickers = set()


async def _report_auth_failure(description: str) -> None:
    from truffile.app_runtime import AppRuntimeErrorType, report_app_error

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


def get_client() -> KalshiClient:
    global _client
    if _client is not None:
        return _client

    config = KalshiConfig.from_env()
    if not config.api_key:
        raise ValueError("Missing KALSHI_API_KEY")
    if not config.private_key_pem:
        raise ValueError("Missing KALSHI_PRIVATE_KEY")

    auth = KalshiAuthProvider(config.api_key, config.private_key_pem)
    _client = KalshiClient(base_url=config.base_url, auth=auth)
    return _client


async def _handle_api_error(error: httpx.HTTPStatusError) -> dict[str, Any]:
    status = error.response.status_code
    if status in {401, 403}:
        try:
            await _report_auth_failure(f"Kalshi API returned {status}")
        except Exception:
            app.logger.exception("Failed to report Kalshi auth failure")

    response_text = ""
    try:
        response_text = error.response.text
    except Exception:
        response_text = ""
    return err(
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
    api = get_client()
    errors: list[str] = []
    warnings: list[str] = []
    estimated_cost = 0
    current_balance = 0

    market_resp = await api.get_market(ticker)
    market = market_resp.get("market") or {}
    market_status = str(market.get("status", "unknown")).lower()
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


class KalshiForegroundApp(ForegroundApp):
    def __init__(self) -> None:
        super().__init__("kalshi", logger_name="kalshi.foreground")
        self._register_tools()

    def _register_tools(self) -> None:
        def tool_description(summary: str, *, params: list[str], example: str) -> str:
            params_block = "\n".join(f"- {line}" for line in params)
            return f"{summary}\n\nParameters:\n{params_block}\n\nExample:\n{example}"

        @self.tool(
            ToolSpec(
                name="get_markets",
                description=tool_description(
                    "Search and list Kalshi prediction markets.",
                    params=[
                        "limit: optional integer from 1 to 40.",
                        "cursor: optional pagination cursor.",
                        "event_ticker: optional event filter.",
                        "series_ticker: optional series filter.",
                        "status: optional one of unopened, open, paused, closed, or settled.",
                        "tickers: optional comma-separated ticker string for exact market filtering.",
                    ],
                    example='get_markets(limit=10, status="open", series_ticker="KXBTCD")',
                ),
                icon=phosphor_icon_url("magnifying-glass"),
            )
        )
        async def get_markets(
            limit: int | None = None,
            cursor: str | None = None,
            event_ticker: str | None = None,
            series_ticker: str | None = None,
            status: str | None = None,
            tickers: str | None = None,
        ) -> dict[str, Any]:
            try:
                _validate_range("limit", limit, 1, 40)
                if status and status not in {"unopened", "open", "paused", "closed", "settled"}:
                    return err("status must be one of unopened|open|paused|closed|settled")
                data = await get_client().get_markets(
                    limit=limit,
                    cursor=cursor,
                    event_ticker=event_ticker,
                    series_ticker=series_ticker,
                    status=status,
                    tickers=tickers,
                )
                markets = data.get("markets", [])
                return ok("Markets fetched", markets=markets, count=len(markets), cursor=data.get("cursor"))
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="get_market",
                description=tool_description(
                    "Get full details for a single market by ticker.",
                    params=["ticker: required market ticker string."],
                    example='get_market(ticker="KXBTCD-26MAR25-B95000")',
                ),
                icon=phosphor_icon_url("magnifying-glass"),
            )
        )
        async def get_market(ticker: str) -> dict[str, Any]:
            try:
                data = await get_client().get_market(ticker)
                market = data.get("market")
                if not market:
                    return err(f"Market not found: {ticker}")
                return ok("Market fetched", market=market)
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="get_orderbook",
                description=tool_description(
                    "Get the orderbook for a market.",
                    params=[
                        "ticker: required market ticker string.",
                        "depth: optional integer from 1 to 100.",
                    ],
                    example='get_orderbook(ticker="KXBTCD-26MAR25-B95000", depth=10)',
                ),
                icon=phosphor_icon_url("book-open-text"),
            )
        )
        async def get_orderbook(ticker: str, depth: int | None = None) -> dict[str, Any]:
            try:
                _validate_range("depth", depth, 1, 100)
                data = await get_client().get_market_orderbook(ticker, depth=depth)
                orderbook = data.get("orderbook")
                if not orderbook:
                    return err(f"Orderbook not found: {ticker}")
                yes_bids = orderbook.get("yes_dollars") or []
                no_bids = orderbook.get("no_dollars") or []
                return ok(
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
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="get_trades",
                description=tool_description(
                    "Get recent public trades for one market or across the exchange.",
                    params=[
                        "ticker: optional market ticker filter.",
                        "limit: optional integer from 1 to 1000.",
                        "cursor: optional pagination cursor.",
                        "min_ts: optional minimum timestamp filter.",
                        "max_ts: optional maximum timestamp filter.",
                    ],
                    example='get_trades(ticker="KXBTCD-26MAR25-B95000", limit=50)',
                ),
                icon=phosphor_icon_url("chart-bar"),
            )
        )
        async def get_trades(
            ticker: str | None = None,
            limit: int | None = None,
            cursor: str | None = None,
            min_ts: int | None = None,
            max_ts: int | None = None,
        ) -> dict[str, Any]:
            try:
                _validate_range("limit", limit, 1, 1000)
                data = await get_client().get_trades(
                    ticker=ticker,
                    limit=limit,
                    cursor=cursor,
                    min_ts=min_ts,
                    max_ts=max_ts,
                )
                trades = data.get("trades", [])
                return ok("Trades fetched", trades=trades, count=len(trades), cursor=data.get("cursor"))
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="get_events",
                description=tool_description(
                    "List Kalshi events, optionally with nested markets.",
                    params=[
                        "limit: optional integer from 1 to 200.",
                        "cursor: optional pagination cursor.",
                        "status: optional one of open, closed, or settled.",
                        "series_ticker: optional series filter.",
                        "with_nested_markets: optional boolean to include event markets.",
                    ],
                    example='get_events(limit=20, status="open", with_nested_markets=true)',
                ),
                icon=phosphor_icon_url("book-open-text"),
            )
        )
        async def get_events(
            limit: int | None = None,
            cursor: str | None = None,
            status: str | None = None,
            series_ticker: str | None = None,
            with_nested_markets: bool | None = None,
        ) -> dict[str, Any]:
            try:
                _validate_range("limit", limit, 1, 200)
                if status and status not in {"open", "closed", "settled"}:
                    return err("status must be one of open|closed|settled")
                data = await get_client().get_events(
                    limit=limit,
                    cursor=cursor,
                    status=status,
                    series_ticker=series_ticker,
                    with_nested_markets=with_nested_markets,
                )
                events = data.get("events", [])
                return ok("Events fetched", events=events, count=len(events), cursor=data.get("cursor"))
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="get_event",
                description=tool_description(
                    "Get details for a single event with optional nested markets.",
                    params=[
                        "event_ticker: required event ticker string.",
                        "with_nested_markets: optional boolean to include event markets.",
                    ],
                    example='get_event(event_ticker="KXBTCD-26MAR25", with_nested_markets=true)',
                ),
                icon=phosphor_icon_url("book-open-text"),
            )
        )
        async def get_event(event_ticker: str, with_nested_markets: bool | None = None) -> dict[str, Any]:
            try:
                data = await get_client().get_event(event_ticker, with_nested_markets=with_nested_markets)
                event = data.get("event")
                if not event:
                    return err(f"Event not found: {event_ticker}")
                markets = data.get("markets") or []
                return ok("Event fetched", event=event, markets=markets, markets_count=len(markets))
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="get_balance",
                description=tool_description(
                    "Get account cash balance and portfolio value.",
                    params=["none"],
                    example="get_balance()",
                ),
                icon=phosphor_icon_url("currency-dollar"),
            )
        )
        async def get_balance() -> dict[str, Any]:
            try:
                data = await get_client().get_balance()
                balance = int(data.get("balance") or 0)
                portfolio_value = int(data.get("portfolio_value") or 0)
                return ok(
                    "Balance fetched",
                    balance_cents=balance,
                    portfolio_value_cents=portfolio_value,
                    balance_dollars=f"{balance / 100:.2f}",
                    portfolio_value_dollars=f"{portfolio_value / 100:.2f}",
                )
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="get_positions",
                description=tool_description(
                    "Get current positions and exposure.",
                    params=[
                        "limit: optional integer from 1 to 100.",
                        "cursor: optional pagination cursor.",
                        "ticker: optional market ticker filter.",
                        "event_ticker: optional event filter.",
                        "count_filter: optional one of position or total_traded.",
                    ],
                    example='get_positions(limit=25, ticker="KXBTCD-26MAR25-B95000")',
                ),
                icon=phosphor_icon_url("chart-line"),
            )
        )
        async def get_positions(
            limit: int | None = None,
            cursor: str | None = None,
            ticker: str | None = None,
            event_ticker: str | None = None,
            count_filter: str | None = None,
        ) -> dict[str, Any]:
            try:
                _validate_range("limit", limit, 1, 100)
                if count_filter and count_filter not in {"position", "total_traded"}:
                    return err("count_filter must be one of position|total_traded")
                data = await get_client().get_positions(
                    limit=limit,
                    cursor=cursor,
                    ticker=ticker,
                    event_ticker=event_ticker,
                    count_filter=count_filter,
                )
                positions = data.get("market_positions", [])
                total_positions = len([p for p in positions if int(p.get("position", 0)) != 0])
                return ok(
                    "Positions fetched",
                    positions=positions,
                    summary={"total_positions": total_positions, "total_returned": len(positions)},
                    cursor=data.get("cursor"),
                )
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="get_orders",
                description=tool_description(
                    "Get order history or active resting orders.",
                    params=[
                        "ticker: optional market ticker filter.",
                        "event_ticker: optional event filter.",
                        "status: optional one of resting, canceled, or executed.",
                        "limit: optional integer from 1 to 200.",
                        "cursor: optional pagination cursor.",
                        "min_ts: optional minimum timestamp filter.",
                        "max_ts: optional maximum timestamp filter.",
                    ],
                    example='get_orders(status="resting", limit=50)',
                ),
                icon=phosphor_icon_url("book-open-text"),
            )
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
            try:
                _validate_range("limit", limit, 1, 200)
                if status and status not in {"resting", "canceled", "executed"}:
                    return err("status must be one of resting|canceled|executed")
                data = await get_client().get_orders(
                    ticker=ticker,
                    event_ticker=event_ticker,
                    status=status,
                    limit=limit,
                    cursor=cursor,
                    min_ts=min_ts,
                    max_ts=max_ts,
                )
                orders = data.get("orders", [])
                return ok(
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
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="create_order",
                description=tool_description(
                    "Place a new order on Kalshi after pre-validation.",
                    params=[
                        "ticker: required market ticker string.",
                        "side: required yes or no.",
                        "action: required buy or sell.",
                        "count: required contract count.",
                        "type: optional limit or market; default limit.",
                        "yes_price: optional yes-side price in cents for yes orders.",
                        "no_price: optional no-side price in cents for no orders.",
                        "client_order_id: optional client-supplied idempotency id.",
                        "expiration_ts: optional expiration timestamp.",
                    ],
                    example='create_order(ticker="KXBTCD-26MAR25-B95000", side="yes", action="buy", count=10, type="limit", yes_price=42)',
                ),
                icon=phosphor_icon_url("plus"),
            )
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
            try:
                if side not in {"yes", "no"}:
                    return err("side must be yes or no")
                if action not in {"buy", "sell"}:
                    return err("action must be buy or sell")
                if type not in {"limit", "market"}:
                    return err("type must be limit or market")
                if side == "yes" and no_price is not None:
                    return err("For side='yes', provide yes_price only")
                if side == "no" and yes_price is not None:
                    return err("For side='no', provide no_price only")
                if type == "limit":
                    if side == "yes" and yes_price is None:
                        return err("For limit yes orders, provide yes_price")
                    if side == "no" and no_price is None:
                        return err("For limit no orders, provide no_price")

                selected_price = yes_price if side == "yes" else no_price
                validation = await _validate_order(
                    ticker=ticker,
                    side=side,
                    action=action,
                    count=count,
                    price=selected_price,
                )
                if not validation["valid"]:
                    return err(
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
                data = await get_client().create_order(payload)
                order = data.get("order")
                if not order:
                    return err("Order created but no order details were returned")
                return ok("Order created successfully", order=order, warnings=validation["warnings"])
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="cancel_order",
                description=tool_description(
                    "Cancel a single resting order.",
                    params=["order_id: required Kalshi order id."],
                    example='cancel_order(order_id="order_123")',
                ),
                icon=phosphor_icon_url("backspace"),
            )
        )
        async def cancel_order(order_id: str) -> dict[str, Any]:
            try:
                data = await get_client().cancel_order(order_id)
                order = data.get("order")
                if not order:
                    return err(f"Order {order_id} canceled but no order details were returned")
                return ok("Order canceled successfully", order=order)
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="batch_cancel_orders",
                description=tool_description(
                    "Cancel up to 20 resting orders in one request.",
                    params=["order_ids: required list of 1 to 20 Kalshi order ids."],
                    example='batch_cancel_orders(order_ids=["order_123","order_456"])',
                ),
                icon=phosphor_icon_url("backspace"),
            )
        )
        async def batch_cancel_orders(order_ids: list[str]) -> dict[str, Any]:
            try:
                if not order_ids:
                    return err("order_ids must contain at least one order ID")
                if len(order_ids) > 20:
                    return err("order_ids cannot exceed 20")
                data = await get_client().batch_cancel_orders(order_ids)
                orders = data.get("orders", [])
                return ok(
                    "Batch cancel executed",
                    cancelled_count=len(orders),
                    requested_count=len(order_ids),
                    cancelled_orders=orders,
                )
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="get_fills",
                description=tool_description(
                    "Get fill history for executed trades.",
                    params=[
                        "ticker: optional market ticker filter.",
                        "order_id: optional order id filter.",
                        "limit: optional integer from 1 to 200.",
                        "cursor: optional pagination cursor.",
                        "min_ts: optional minimum timestamp filter.",
                        "max_ts: optional maximum timestamp filter.",
                    ],
                    example='get_fills(ticker="KXBTCD-26MAR25-B95000", limit=100)',
                ),
                icon=phosphor_icon_url("book-open-text"),
            )
        )
        async def get_fills(
            ticker: str | None = None,
            order_id: str | None = None,
            limit: int | None = None,
            cursor: str | None = None,
            min_ts: int | None = None,
            max_ts: int | None = None,
        ) -> dict[str, Any]:
            try:
                _validate_range("limit", limit, 1, 200)
                data = await get_client().get_fills(
                    ticker=ticker,
                    order_id=order_id,
                    limit=limit,
                    cursor=cursor,
                    min_ts=min_ts,
                    max_ts=max_ts,
                )
                fills = data.get("fills", [])
                return ok(
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
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="get_settlements",
                description=tool_description(
                    "Get settlement history for resolved markets.",
                    params=[
                        "ticker: optional market ticker filter.",
                        "event_ticker: optional event filter.",
                        "limit: optional integer from 1 to 200.",
                        "cursor: optional pagination cursor.",
                        "min_ts: optional minimum timestamp filter.",
                        "max_ts: optional maximum timestamp filter.",
                    ],
                    example='get_settlements(event_ticker="KXBTCD-26MAR25", limit=50)',
                ),
                icon=phosphor_icon_url("book-open-text"),
            )
        )
        async def get_settlements(
            ticker: str | None = None,
            event_ticker: str | None = None,
            limit: int | None = None,
            cursor: str | None = None,
            min_ts: int | None = None,
            max_ts: int | None = None,
        ) -> dict[str, Any]:
            try:
                _validate_range("limit", limit, 1, 200)
                data = await get_client().get_settlements(
                    ticker=ticker,
                    event_ticker=event_ticker,
                    limit=limit,
                    cursor=cursor,
                    min_ts=min_ts,
                    max_ts=max_ts,
                )
                settlements = data.get("settlements", [])
                total_revenue = sum(int(s.get("revenue") or 0) for s in settlements)
                return ok(
                    "Settlements fetched",
                    settlements=settlements,
                    summary={
                        "total": len(settlements),
                        "total_revenue_cents": total_revenue,
                        "total_revenue_dollars": f"{total_revenue / 100:.2f}",
                        "profitable_settlements": len(
                            [s for s in settlements if int(s.get("revenue") or 0) > 0]
                        ),
                    },
                    cursor=data.get("cursor"),
                )
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="get_portfolio_summary",
                description=tool_description(
                    "Get a complete portfolio overview in one call.",
                    params=["none"],
                    example="get_portfolio_summary()",
                ),
                icon=phosphor_icon_url("book-open-text"),
            )
        )
        async def get_portfolio_summary() -> dict[str, Any]:
            try:
                api = get_client()
                balance_data = await api.get_balance()
                positions_data = await api.get_positions(limit=100)
                positions = positions_data.get("market_positions", [])

                enriched: list[dict[str, Any]] = []
                for pos in positions:
                    count = int(pos.get("position", 0))
                    if count == 0:
                        continue
                    ticker = pos.get("ticker", "")
                    market_info: dict[str, Any] = {}
                    try:
                        market_resp = await api.get_market(ticker)
                        market_info = market_resp.get("market", {})
                    except Exception:
                        market_info = {}
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
                return ok(
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
                return err(str(error))

        @self.tool(
            ToolSpec(
                name="watchlist_manage",
                description=tool_description(
                    "Manage foreground watchlist metadata for Kalshi tickers.",
                    params=[
                        "action: required one of list, add, remove, or clear.",
                        "tickers: optional list of ticker strings; required for add and remove.",
                    ],
                    example='watchlist_manage(action="add", tickers=["KXBTCD-26MAR25-B95000","KXETH-26MAR25-B3200"])',
                ),
                icon=phosphor_icon_url("list-dashes"),
            )
        )
        async def watchlist_manage(action: str, tickers: list[str] | None = None) -> dict[str, Any]:
            global _watched_tickers
            normalized_action = action.strip().lower()

            if normalized_action == "list":
                return ok(
                    f"Watching {len(_watched_tickers)} tickers",
                    watched_tickers=sorted(_watched_tickers),
                )
            if normalized_action == "add":
                if not tickers:
                    return err("tickers list required for add")
                for ticker in tickers:
                    cleaned = ticker.strip().upper()
                    if cleaned:
                        _watched_tickers.add(cleaned)
                return ok(
                    f"Added {len(tickers)} tickers, now watching {len(_watched_tickers)}",
                    watched_tickers=sorted(_watched_tickers),
                )
            if normalized_action == "remove":
                if not tickers:
                    return err("tickers list required for remove")
                for ticker in tickers:
                    cleaned = ticker.strip().upper()
                    if cleaned:
                        _watched_tickers.discard(cleaned)
                return ok(
                    f"Removed tickers, now watching {len(_watched_tickers)}",
                    watched_tickers=sorted(_watched_tickers),
                )
            if normalized_action == "clear":
                _watched_tickers.clear()
                return ok("Watchlist cleared", watched_tickers=[])
            return err(f"Unknown action: {action}. Use list, add, remove, or clear.")

        @self.tool(
            ToolSpec(
                name="kalshi_health",
                description=tool_description(
                    "Check health of Kalshi API connection and credentials.",
                    params=["none"],
                    example="kalshi_health()",
                ),
                icon=phosphor_icon_url("heartbeat"),
            )
        )
        async def kalshi_health() -> dict[str, Any]:
            try:
                data = await get_client().get_balance()
                balance = int(data.get("balance", 0))
                return ok(
                    "Kalshi API healthy",
                    api_healthy=True,
                    balance_cents=balance,
                    balance_dollars=f"{balance / 100:.2f}",
                )
            except httpx.HTTPStatusError as error:
                return await _handle_api_error(error)
            except Exception as error:
                return err(str(error), api_healthy=False)


async def _cleanup() -> None:
    global _client
    if _client is None:
        return
    try:
        await _client.close()
    finally:
        _client = None


def _cleanup_sync() -> None:
    try:
        asyncio.run(_cleanup())
    except Exception:
        pass


app = KalshiForegroundApp()


if __name__ == "__main__":
    atexit.register(_cleanup_sync)
    app.run()
