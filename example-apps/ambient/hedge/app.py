import os
import requests
import urllib.parse
from datetime import datetime
from gourmet.ambient import run_ambient, AmbientContext
import logging

logger = logging.getLogger("hedge")
logger.setLevel(logging.DEBUG)

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "go get your key dudes")
TICKERS = os.getenv("HEDGE_TICKERS", "AAPL,MSFT,GOOGL,IREN").split(",")
BASE_URL = "https://www.alphavantage.co/query"


def fetch_daily_data(symbol: str) -> dict | None:
    try:
        resp = requests.get(BASE_URL, params={
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol.strip().upper(),
            "outputsize": "compact",
            "apikey": API_KEY,
        }, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "Time Series (Daily)" not in data:
            logger.warning(f"No daily data for {symbol}: {data}")
            return None
        return data
    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {e}")
        return None


def generate_chart_url(symbol: str, dates: list[str], prices: list[float]) -> str:
    chart_config = {
        "type": "line",
        "data": {
            "labels": dates,
            "datasets": [{
                "label": symbol,
                "data": prices,
                "fill": False,
                "borderColor": "#4CAF50",
                "tension": 0.1,
                "pointRadius": 2,
            }]
        },
        "options": {
            "plugins": {
                "legend": {"display": False},
                "title": {"display": True, "text": f"{symbol} - Last 5 Days"}
            },
            "scales": {
                "y": {"beginAtZero": False}
            }
        }
    }
    chart_json = str(chart_config).replace("'", '"').replace("False", "false").replace("True", "true")
    encoded = urllib.parse.quote(chart_json, safe='')
    return f"https://quickchart.io/chart?c={encoded}&w=400&h=200&bkg=white"


def hedge_ambient(ctx: AmbientContext):
    logger.info(f"Hedge running for tickers: {TICKERS}")
    
    for symbol in TICKERS:
        symbol = symbol.strip().upper()
        if not symbol:
            continue
            
        data = fetch_daily_data(symbol)
        if not data:
            continue
        
        ts = data["Time Series (Daily)"]
        sorted_dates = sorted(ts.keys(), reverse=True)[:5]
        sorted_dates.reverse()
        
        dates = [d[5:] for d in sorted_dates]
        prices = [float(ts[d]["4. close"]) for d in sorted_dates]
        
        today = sorted_dates[-1]
        today_data = ts[today]
        current_price = float(today_data["4. close"])
        open_price = float(today_data["1. open"])
        high = float(today_data["2. high"])
        low = float(today_data["3. low"])
        volume = int(today_data["5. volume"])
        
        change = current_price - open_price
        change_pct = (change / open_price) * 100 if open_price else 0
        arrow = "📈" if change >= 0 else "📉"
        
        chart_url = generate_chart_url(symbol, dates, prices)
        
        title = f"{arrow} {symbol}: ${current_price:.2f}"
        body = f"""
{symbol} Stock Update

Price: ${current_price:.2f}
Change: {'+' if change >= 0 else ''}{change:.2f} ({'+' if change_pct >= 0 else ''}{change_pct:.2f}%)

Today's Range: ${low:.2f} - ${high:.2f}
Volume: {volume:,}
""".strip()
        
        logger.info(f"Posting {symbol} to feed: {title}")
        ctx.bg.post_to_feed(
            title=title,
            body=body,
            src_uri=f"https://finance.yahoo.com/quote/{symbol}",
            media_uris=[chart_url],
            content_timestamp=datetime.now()
        )
        logger.info(f"Posted {symbol} to feed")


if __name__ == "__main__":
    run_ambient(hedge_ambient)
