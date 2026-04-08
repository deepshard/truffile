from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import os
from typing import Optional

logger = logging.getLogger("reddit")
logger.setLevel(logging.INFO)

DEFAULT_SUBREDDITS = ["news", "worldnews", "all"]
DEFAULT_SORT = "hot"
POST_LIMIT = 32

MODE_FULL = "full"
MODE_COMPACT = "compact"
DEFAULT_MODE = MODE_COMPACT
DEFAULT_POSTS_PER_CYCLE = 8

TOP_COMMENTS_TO_INCLUDE = 10
MAX_COMMENT_LEN_CHARS = 4000

_EMPTY_ENV_VALUES = {"", "none", "null", "undefined", "n/a"}


def parse_subreddits(raw: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for part in raw.split(","):
        subreddit = part.strip()
        if not subreddit:
            continue
        lowered = subreddit.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(subreddit)
    return ordered


def normalize_user_feed_url(raw: str, *, sort: str = DEFAULT_SORT) -> str | None:
    candidate = raw.strip()
    if candidate.lower() in _EMPTY_ENV_VALUES:
        return None
    if not (candidate.startswith("http://") or candidate.startswith("https://")):
        logger.warning("Invalid USER_FEED_URL format, ignoring: %s", candidate)
        return None
    if "reddit.com" not in candidate:
        logger.warning("USER_FEED_URL does not appear to be a reddit.com URL, ignoring: %s", candidate)
        return None
    if ".rss" in candidate:
        logger.warning("USER_FEED_URL appears to be an RSS feed, converting it to JSON: %s", candidate)
        candidate = candidate.replace(".rss", ".json")
    if ".json?feed=" not in candidate:
        logger.warning("USER_FEED_URL does not appear to be a reddit JSON feed URL, ignoring: %s", candidate)
        return None
    if "user=" not in candidate:
        logger.warning("USER_FEED_URL does not appear to be a user feed URL, ignoring: %s", candidate)
        return None
    if f"/{sort}/.json" in candidate:
        return candidate
    dotjson_index = candidate.find("/.json")
    if dotjson_index == -1:
        logger.warning("Could not find /.json in USER_FEED_URL, could not add sort: %s", candidate)
        return candidate
    return f"{candidate[:dotjson_index]}/{sort}{candidate[dotjson_index:]}"


@dataclass(slots=True)
class RedditConfig:
    subreddits: list[str]
    user_feed_url: str | None
    sort: str = DEFAULT_SORT
    post_limit: int = POST_LIMIT
    mode: str = DEFAULT_MODE
    posts_per_cycle: int = DEFAULT_POSTS_PER_CYCLE

    @classmethod
    def from_env(cls) -> RedditConfig:
        subreddits = parse_subreddits(os.getenv("SUBREDDITS", "").strip())
        if not subreddits:
            subreddits = list(DEFAULT_SUBREDDITS)
        user_feed_url = normalize_user_feed_url(os.getenv("USER_FEED_URL", ""), sort=DEFAULT_SORT)
        mode = os.getenv("REDDIT_MODE", DEFAULT_MODE).strip().lower()
        if mode not in (MODE_FULL, MODE_COMPACT):
            logger.warning("Unknown REDDIT_MODE '%s', defaulting to '%s'", mode, DEFAULT_MODE)
            mode = DEFAULT_MODE
        try:
            posts_per_cycle = int(os.getenv("REDDIT_POSTS_PER_RUN", str(DEFAULT_POSTS_PER_CYCLE)))
        except ValueError:
            posts_per_cycle = DEFAULT_POSTS_PER_CYCLE
        return cls(
            subreddits=subreddits,
            user_feed_url=user_feed_url,
            mode=mode,
            posts_per_cycle=max(1, posts_per_cycle),
        )

    def get_listing_url(self) -> str:
        if self.user_feed_url:
            return self.user_feed_url
        return f"https://www.reddit.com/r/{'+'.join(self.subreddits)}/{self.sort}/.json"


@dataclass(slots=True)
class RedditPost:
    fullname: str
    id: str
    title: str
    subreddit: str
    permalink: str
    comments_url: str
    article_url: str
    image_urls: list[str] | None
    score: int
    num_comments: int
    created_utc: datetime
    domain: str


@dataclass(slots=True)
class RedditComment:
    id: str
    author: Optional[str]
    body: str
    score: Optional[int]
    permalink: str


def created_datetime_from_epoch(value: float | int | None) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    created = float(value)
    if created <= 0.0:
        return datetime.now(tz=UTC)
    return datetime.fromtimestamp(created, tz=UTC)
