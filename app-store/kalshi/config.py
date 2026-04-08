"""Configuration helpers for the Kalshi Truffle app."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


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

DEFAULT_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


def parse_categories(raw: str) -> set[str]:
    categories: set[str] = {"trending"}
    if not raw.strip():
        return categories
    for cat in raw.split(","):
        cleaned = cat.strip().lower()
        if cleaned in CATEGORY_KEYWORDS:
            categories.add(cleaned)
    return categories


def normalize_private_key(raw: str | None) -> str:
    key = (raw or "").strip()
    if "\\n" in key:
        key = key.replace("\\n", "\n")
    return key


@dataclass(frozen=True, slots=True)
class KalshiConfig:
    api_key: str = ""
    private_key_pem: str = ""
    base_url: str = DEFAULT_BASE_URL
    categories: set[str] = field(default_factory=lambda: {"trending"})
    feed_url: str = ""
    watched_tickers: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> KalshiConfig:
        return cls(
            api_key=os.getenv("KALSHI_API_KEY", "").strip(),
            private_key_pem=normalize_private_key(os.getenv("KALSHI_PRIVATE_KEY", "")),
            base_url=os.getenv("KALSHI_BASE_PATH", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
            categories=parse_categories(os.getenv("KALSHI_CATEGORIES", "")),
            feed_url=os.getenv("KALSHI_FEED_URL", "").strip(),
        )
