"""Configuration for the Kalshi Truffle app."""

from __future__ import annotations

import os

KALSHI_API_KEY: str = os.getenv("KALSHI_API_KEY", "")
KALSHI_PRIVATE_KEY: str = os.getenv("KALSHI_PRIVATE_KEY", "")
KALSHI_BASE_URL: str = os.getenv(
    "KALSHI_BASE_PATH",
    "https://api.elections.kalshi.com/trade-api/v2",
)

DEFAULT_WATCHED_TICKERS: list[str] = []

KALSHI_CATEGORIES_RAW: str = os.getenv("KALSHI_CATEGORIES", "")
KALSHI_FEED_URL: str = os.getenv("KALSHI_FEED_URL", "").strip()

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "politics": [
        "president", "election", "nominee", "senate", "house", "governor",
        "congress", "democrat", "republican", "vote", "party", "cabinet",
        "trump", "biden", "vance",
    ],
    "sports": [
        "nfl", "nba", "mlb", "nhl", "super bowl", "world series",
        "championship", "ufc", "boxing", "playoffs", "soccer", "fifa",
    ],
    "culture": [
        "oscar", "grammy", "emmy", "movie", "film", "music",
        "celebrity", "award", "entertainment", "streaming",
    ],
    "crypto": [
        "bitcoin", "btc", "ethereum", "eth", "crypto", "solana",
        "dogecoin", "blockchain",
    ],
    "climate": [
        "temperature", "weather", "hurricane", "climate", "wildfire",
        "flood", "drought", "storm", "tornado",
    ],
    "economics": [
        "gdp", "inflation", "cpi", "fed", "interest rate", "unemployment",
        "recession", "gas price", "oil", "spending", "treasury",
    ],
    "mentions": [
        "mention", "say", "speech", "briefing", "address",
        "state of the union",
    ],
    "companies": [
        "company", "stock", "ipo", "acquisition", "merger", "earnings",
        "tesla", "apple", "google", "amazon", "meta",
    ],
    "financials": [
        "s&p", "dow", "nasdaq", "index", "bond", "yield", "forex",
        "close price",
    ],
    "tech & science": [
        "ai", "technology", "science", "space", "nasa", "launch",
        "starship", "openai", "quantum",
    ],
}


def parse_categories(raw: str) -> set[str]:
    categories: set[str] = {"trending"}
    if not raw.strip():
        return categories
    for cat in raw.split(","):
        cleaned = cat.strip().lower()
        if cleaned in CATEGORY_KEYWORDS:
            categories.add(cleaned)
    return categories


KALSHI_CATEGORIES: set[str] = parse_categories(KALSHI_CATEGORIES_RAW)


def normalize_private_key(raw: str) -> str:
    """Normalize a pasted PEM key from env text fields."""
    key = (raw or "").strip()
    if "\\n" in key:
        key = key.replace("\\n", "\n")
    return key
