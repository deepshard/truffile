import requests
from mcp.server.fastmcp import FastMCP

API_KEY = "nope"
BASE_URL = "https://www.alphavantage.co/query"

HOST = "0.0.0.0"
PORT = 8000

mcp = FastMCP("finance", stateless_http=True, host=HOST, port=PORT)


def _call_av(function: str, **params) -> dict:
    params["function"] = function
    params["apikey"] = API_KEY
    resp = requests.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


@mcp.tool("get_stock_price", description="Get current price and daily stats for a stock ticker (e.g. AAPL, MSFT, TSLA)")
async def get_stock_price(symbol: str) -> str:
    data = _call_av("GLOBAL_QUOTE", symbol=symbol.upper())
    quote = data.get("Global Quote", {})
    if not quote:
        return f"No data found for {symbol}"
    return f"""
{quote.get('01. symbol', symbol)}
Price: ${quote.get('05. price', 'N/A')}
Change: {quote.get('09. change', 'N/A')} ({quote.get('10. change percent', 'N/A')})
Open: ${quote.get('02. open', 'N/A')}
High: ${quote.get('03. high', 'N/A')}
Low: ${quote.get('04. low', 'N/A')}
Volume: {quote.get('06. volume', 'N/A')}
Previous Close: ${quote.get('08. previous close', 'N/A')}
""".strip()


@mcp.tool("get_stock_history", description="Get daily price history for a stock. Returns last 30 days by default.")
async def get_stock_history(symbol: str, days: int = 30) -> str:
    data = _call_av("TIME_SERIES_DAILY", symbol=symbol.upper(), outputsize="compact")
    ts = data.get("Time Series (Daily)", {})
    if not ts:
        return f"No historical data for {symbol}"
    lines = [f"{symbol.upper()} - Last {min(days, len(ts))} trading days:"]
    for i, (date, vals) in enumerate(sorted(ts.items(), reverse=True)):
        if i >= days:
            break
        lines.append(f"{date}: Open ${vals['1. open']} | High ${vals['2. high']} | Low ${vals['3. low']} | Close ${vals['4. close']} | Vol {vals['5. volume']}")
    return "\n".join(lines)


@mcp.tool("get_company_overview", description="Get company profile, financials, and key metrics for a stock")
async def get_company_overview(symbol: str) -> str:
    data = _call_av("OVERVIEW", symbol=symbol.upper())
    if not data or "Symbol" not in data:
        return f"No company data for {symbol}"
    return f"""
{data.get('Name', symbol)} ({data.get('Symbol', '')})
Sector: {data.get('Sector', 'N/A')} | Industry: {data.get('Industry', 'N/A')}
Market Cap: ${data.get('MarketCapitalization', 'N/A')}
P/E Ratio: {data.get('PERatio', 'N/A')} | EPS: ${data.get('EPS', 'N/A')}
52-Week High: ${data.get('52WeekHigh', 'N/A')} | 52-Week Low: ${data.get('52WeekLow', 'N/A')}
Dividend Yield: {data.get('DividendYield', 'N/A')}
Description: {data.get('Description', 'N/A')[:500]}...
""".strip()


@mcp.tool("search_ticker", description="Search for stock ticker symbols by company name or keywords")
async def search_ticker(keywords: str) -> str:
    data = _call_av("SYMBOL_SEARCH", keywords=keywords)
    matches = data.get("bestMatches", [])
    if not matches:
        return f"No matches for '{keywords}'"
    lines = [f"Search results for '{keywords}':"]
    for m in matches[:10]:
        lines.append(f"  {m.get('1. symbol', '')} - {m.get('2. name', '')} ({m.get('4. region', '')})")
    return "\n".join(lines)


@mcp.tool("get_market_news", description="Get latest market news and sentiment for a stock or topic")
async def get_market_news(tickers: str = "", topics: str = "", limit: int = 5) -> str:
    params = {"limit": min(limit, 50)}
    if tickers:
        params["tickers"] = tickers.upper()
    if topics:
        params["topics"] = topics
    data = _call_av("NEWS_SENTIMENT", **params)
    feed = data.get("feed", [])
    if not feed:
        return "No news found"
    lines = ["Latest Market News:"]
    for article in feed[:limit]:
        sentiment = article.get("overall_sentiment_label", "")
        lines.append(f"[{sentiment}] {article.get('title', 'No title')}")
        lines.append(f"  Source: {article.get('source', 'Unknown')} | {article.get('time_published', '')[:10]}")
        lines.append(f"  {article.get('summary', '')[:200]}...")
        lines.append("")
    return "\n".join(lines)


@mcp.tool("get_top_movers", description="Get top gainers, losers, and most actively traded stocks today")
async def get_top_movers() -> str:
    data = _call_av("TOP_GAINERS_LOSERS")
    lines = []
    for category in ["top_gainers", "top_losers", "most_actively_traded"]:
        items = data.get(category, [])[:5]
        if items:
            lines.append(f"\n{category.replace('_', ' ').title()}:")
            for item in items:
                lines.append(f"  {item.get('ticker', '')} ${item.get('price', '')} ({item.get('change_percentage', '')})")
    return "\n".join(lines).strip() or "No market data available"


@mcp.tool("get_crypto_price", description="Get current exchange rate for a cryptocurrency (e.g. BTC, ETH)")
async def get_crypto_price(crypto: str, currency: str = "USD") -> str:
    data = _call_av("CURRENCY_EXCHANGE_RATE", from_currency=crypto.upper(), to_currency=currency.upper())
    rate = data.get("Realtime Currency Exchange Rate", {})
    if not rate:
        return f"No data for {crypto}/{currency}"
    return f"""
{rate.get('1. From_Currency Code', crypto)} → {rate.get('3. To_Currency Code', currency)}
Rate: {rate.get('5. Exchange Rate', 'N/A')}
Bid: {rate.get('8. Bid Price', 'N/A')} | Ask: {rate.get('9. Ask Price', 'N/A')}
Last Updated: {rate.get('6. Last Refreshed', 'N/A')}
""".strip()


@mcp.tool("get_economic_indicator", description="Get economic indicators: GDP, CPI, UNEMPLOYMENT, INTEREST_RATE, INFLATION")
async def get_economic_indicator(indicator: str) -> str:
    indicator = indicator.upper()
    func_map = {
        "GDP": "REAL_GDP",
        "CPI": "CPI",
        "UNEMPLOYMENT": "UNEMPLOYMENT",
        "INTEREST_RATE": "FEDERAL_FUNDS_RATE",
        "INFLATION": "INFLATION",
    }
    func = func_map.get(indicator, indicator)
    data = _call_av(func)
    vals = data.get("data", [])[:10]
    if not vals:
        return f"No data for {indicator}"
    name = data.get("name", indicator)
    lines = [f"{name}:"]
    for v in vals:
        lines.append(f"  {v.get('date', '')}: {v.get('value', 'N/A')}")
    return "\n".join(lines)


def main():
    print(f"Starting Finance MCP server on {HOST}:{PORT}")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
