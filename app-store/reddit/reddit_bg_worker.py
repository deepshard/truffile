from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import logging
import time
from typing import Any, Deque

import requests
from truffile.app_runtime.abrasive.extract import ExtractedContent, extract_content_from_url
from truffile.app_runtime.abrasive.fetch import USER_AGENT
from truffle.app.background_pb2 import BackgroundContext

from reddit_common import (
    MAX_COMMENT_LEN_CHARS,
    MODE_COMPACT,
    POST_LIMIT,
    TOP_COMMENTS_TO_INCLUDE,
    RedditComment,
    RedditConfig,
    RedditPost,
    created_datetime_from_epoch,
)

logger = logging.getLogger("reddit.bg_worker")
logger.setLevel(logging.INFO)

REDDIT_JSON_REQUESTS_PER_MINUTE = 10
REDDIT_JSON_RATE_LIMIT_SECONDS = 60 / REDDIT_JSON_REQUESTS_PER_MINUTE
_PRIORITY_LOW = getattr(
    BackgroundContext,
    "PRIORITY_LOW",
    getattr(BackgroundContext, "PRIORITY_DEFAULT", 0),
)


@dataclass(slots=True)
class PreparedSubmission:
    text: str
    uris: tuple[str, ...]
    priority: int = _PRIORITY_LOW


@dataclass(slots=True)
class BgRunResult:
    submissions: list[PreparedSubmission]
    error: str | None = None


class RedditBackgroundWorker:
    def __init__(self, *, config: RedditConfig | None = None) -> None:
        self.config = config or RedditConfig.from_env()
        self._seen_reddit: set[str] = set()
        self._pending_reddit: Deque[RedditPost] = deque()
        self._listing_after: str | None = None
        self._listing_after_fp: str | None = None
        self._last_request_time = time.monotonic() - REDDIT_JSON_RATE_LIMIT_SECONDS

    def verify(self) -> tuple[bool, str]:
        ok = self.validate_config()
        if ok:
            return True, f"Reddit configuration valid: {self.config}"
        return False, "Reddit configuration invalid. Please check the subreddit list or personal feed URL."

    def validate_config(self) -> bool:
        try:
            response = self.reddit_request(self.config.get_listing_url(), params={"limit": 1}, timeout=10)
            data = response.json()
            if not isinstance(data, dict) or "data" not in data:
                logger.error("Reddit config validation failed: response did not include a data object")
                return False
            return True
        except Exception as exc:
            logger.error("Reddit config validation error: %s", exc, exc_info=True)
            return False

    def run_cycle(self) -> BgRunResult:
        submissions: list[PreparedSubmission] = []
        is_compact = self.config.mode == MODE_COMPACT
        for _ in range(self.config.posts_per_cycle):
            item = self._next_new_reddit_item()
            if item is None:
                break
            if is_compact:
                submissions.append(self.prepare_submission_compact(item))
            else:
                submissions.append(self.prepare_submission(item))
        return BgRunResult(submissions=submissions)

    def reddit_request(self, url: str, *, params: dict[str, Any], timeout: int = 10) -> requests.Response:
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < REDDIT_JSON_RATE_LIMIT_SECONDS:
            time.sleep((REDDIT_JSON_RATE_LIMIT_SECONDS - elapsed) + 0.25)
        self._last_request_time = time.monotonic()
        headers = {
            "User-Agent": USER_AGENT,
            "Connection": "close",
        }
        logger.info("Reddit JSON request to %s with params %s", url, params)
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response

    def _fetch_listing(self, *, after: str | None = None) -> tuple[list[RedditPost], str | None]:
        params: dict[str, Any] = {
            "limit": self.config.post_limit or POST_LIMIT,
            "sort": "new",
        }
        if after:
            params["after"] = after

        response = self.reddit_request(self.config.get_listing_url(), params=params, timeout=10)
        data = response.json()["data"]
        children = data.get("children", [])
        after_token = data.get("after")

        posts: list[RedditPost] = []
        for child in children:
            if child.get("kind") != "t3":
                continue
            post_data: dict[str, Any] = child["data"]
            fullname = str(post_data.get("name") or "").strip()
            if not fullname:
                continue

            permalink = str(post_data.get("permalink") or "")
            comments_url = f"https://www.reddit.com{permalink}" if permalink else ""
            article_url = str(post_data.get("url_overridden_by_dest") or post_data.get("url") or "")

            image_urls = self._extract_image_urls(post_data)

            posts.append(
                RedditPost(
                    fullname=fullname,
                    id=str(post_data.get("id") or ""),
                    title=str(post_data.get("title") or ""),
                    subreddit=str(post_data.get("subreddit") or ""),
                    permalink=permalink,
                    comments_url=comments_url,
                    article_url=article_url,
                    image_urls=image_urls or None,
                    score=int(post_data.get("score") or 0),
                    num_comments=int(post_data.get("num_comments") or 0),
                    created_utc=created_datetime_from_epoch(post_data.get("created_utc")),
                    domain=str(post_data.get("domain") or ""),
                )
            )

        return posts, after_token

    def _extract_image_urls(self, post_data: dict[str, Any]) -> list[str]:
        image_urls: list[str] = []
        preview = post_data.get("preview")
        if isinstance(preview, dict):
            for image in preview.get("images", []) or []:
                if not isinstance(image, dict):
                    continue
                source = image.get("source")
                if isinstance(source, dict):
                    url = source.get("url")
                    if isinstance(url, str) and url:
                        image_urls.append(url.replace("&amp;", "&"))

        if image_urls:
            return image_urls

        thumbnail = post_data.get("thumbnail")
        if isinstance(thumbnail, str) and thumbnail.startswith("http"):
            image_urls.append(thumbnail.replace("&amp;", "&"))
        return image_urls

    def _refill_from_frontpage(self) -> bool:
        posts, after_token = self._fetch_listing(after=None)
        self._listing_after_fp = after_token
        return self._enqueue_unseen(posts, source="frontpage")

    def _refill_from_older(self) -> bool:
        posts, after_token = self._fetch_listing(after=self._listing_after)
        self._listing_after = after_token
        return self._enqueue_unseen(posts, source="older")

    def _enqueue_unseen(self, posts: list[RedditPost], *, source: str) -> bool:
        added = 0
        for post in posts:
            if post.fullname in self._seen_reddit:
                continue
            self._pending_reddit.append(post)
            added += 1
        logger.info("Reddit %s refill added %d posts", source, added)
        return added > 0

    def _refill_reddit(self) -> None:
        if self._refill_from_frontpage():
            return
        self._refill_from_older()

    def _next_new_reddit_item(self) -> RedditPost | None:
        if not self._pending_reddit:
            self._refill_reddit()

        if not self._pending_reddit:
            return None

        item = self._pending_reddit.popleft()
        self._seen_reddit.add(item.fullname)
        return item

    def fetch_post_comments(self, post: RedditPost, *, max_top: int = 10) -> list[RedditComment]:
        if not post.permalink:
            return []

        url = f"https://www.reddit.com{post.permalink.rstrip('/')}.json"
        response = self.reddit_request(url, params={"sort": "top", "limit": 50}, timeout=10)
        payload = response.json()
        if not isinstance(payload, list) or len(payload) < 2:
            return []

        comments_listing = payload[1]["data"]["children"]

        comments: list[RedditComment] = []
        for child in comments_listing:
            if child.get("kind") != "t1":
                continue
            comment_data = child["data"]
            body = comment_data.get("body")
            if not isinstance(body, str) or not body.strip():
                continue
            permalink = str(comment_data.get("permalink") or "")
            comments.append(
                RedditComment(
                    id=str(comment_data.get("id") or ""),
                    author=comment_data.get("author"),
                    body=body,
                    score=comment_data.get("score"),
                    permalink=f"https://www.reddit.com{permalink}" if permalink else "",
                )
            )

        if not comments:
            return []

        comments.sort(key=lambda comment: (comment.score or 0), reverse=True)
        top = comments[:max_top]
        worst = min(comments, key=lambda comment: (comment.score or 0))
        if worst not in top and len(top) < max_top + 1:
            top.append(worst)
        return top

    def get_content_for_reddit_item(self, item: RedditPost) -> tuple[ExtractedContent | None, list[RedditComment]]:
        try:
            link_content = None
            if item.article_url and not item.domain.startswith("self."):
                link_content = extract_content_from_url(item.article_url)
            comments = self.fetch_post_comments(item, max_top=10)
            return link_content, comments
        except Exception as exc:
            logger.error("Error fetching content for %s: %s", item.fullname, exc, exc_info=True)
            return None, []

    def prepare_submission(self, item: RedditPost) -> PreparedSubmission:
        """Full mode: fetch article + comments, rich XML-tagged context."""
        logger.info(
            "Processing Reddit item %s: %s (%s) %s %s",
            item.fullname,
            item.title,
            item.article_url,
            item.subreddit,
            item.image_urls or [],
        )
        link_content, comments = self.get_content_for_reddit_item(item)
        content = self._build_full_text(item=item, link_content=link_content, comments=comments)

        uris: list[str] = []
        if item.article_url:
            uris.append(item.article_url)
        if link_content and getattr(link_content, "source_url", None) and link_content.source_url != item.article_url:
            uris.append(link_content.source_url)

        return PreparedSubmission(text=content, uris=tuple(uris), priority=_PRIORITY_LOW)

    def prepare_submission_compact(self, item: RedditPost) -> PreparedSubmission:
        """Compact mode: fetch article but skip comments. Denser output."""
        logger.info(
            "Processing Reddit item (compact) %s: %s (%s)",
            item.fullname,
            item.title,
            item.article_url,
        )
        link_content: ExtractedContent | None = None
        if item.article_url and not item.domain.startswith("self."):
            try:
                link_content = extract_content_from_url(item.article_url)
            except Exception as exc:
                logger.error("Error fetching article for %s: %s", item.fullname, exc, exc_info=True)

        content = self._build_compact_text(item=item, link_content=link_content)

        uris: list[str] = []
        if item.article_url:
            uris.append(item.article_url)
        if item.comments_url:
            uris.append(item.comments_url)

        return PreparedSubmission(text=content, uris=tuple(uris), priority=_PRIORITY_LOW)

    def _build_post_metadata(self, item: RedditPost) -> list[str]:
        parts: list[str] = [
            "<reddit_post>",
            f"<subreddit>{item.subreddit}</subreddit>",
            f"<title>{item.title}</title>",
            f"<domain>{item.domain}</domain>",
            f"<score>{item.score}</score>",
            f"<num_comments>{item.num_comments}</num_comments>",
            f"<created_utc>{item.created_utc.isoformat()}</created_utc>",
        ]
        if item.article_url:
            parts.append(f"<link_url>{item.article_url}</link_url>")
        parts.append(f"<comments_url>{item.comments_url}</comments_url>")

        if item.image_urls:
            parts.append("<images>")
            for img_url in item.image_urls:
                parts.append(f"  <image_url>{img_url}</image_url>")
            parts.append("</images>")

        return parts

    def _build_linked_article_section(
        self, link_content: ExtractedContent, *, article_url: str
    ) -> list[str]:
        parts: list[str] = ["<linked_article>"]
        title = getattr(link_content, "title", None)
        if title:
            parts.append(f"  <article_title>{title}</article_title>")
        date = getattr(link_content, "date", None)
        if date:
            parts.append(f"  <article_date>{date}</article_date>")
        source_name = getattr(link_content, "source_name", None)
        if source_name:
            parts.append(f"  <article_source>{source_name}</article_source>")
        source_url = getattr(link_content, "source_url", None)
        if source_url and source_url != article_url:
            parts.append(f"  <article_canonical_url>{source_url}</article_canonical_url>")
        parts.append(f"  <article_body>{link_content.text}</article_body>")
        parts.append("</linked_article>")
        return parts

    def _build_full_text(
        self,
        *,
        item: RedditPost,
        link_content: ExtractedContent | None,
        comments: list[RedditComment],
    ) -> str:
        parts = self._build_post_metadata(item)

        if link_content and getattr(link_content, "text", None):
            parts.extend(self._build_linked_article_section(link_content, article_url=item.article_url))

        if comments:
            parts.append("<top_comments>")
            comments_included = 0
            comments_total_chars = 0
            for comment in comments:
                if comments_included >= TOP_COMMENTS_TO_INCLUDE and comments_total_chars >= MAX_COMMENT_LEN_CHARS:
                    break
                comment_parts = ["  <comment>"]
                if comment.author:
                    comment_parts.append(f"    <author>{comment.author}</author>")
                if comment.score is not None:
                    comment_parts.append(f"    <score>{comment.score}</score>")
                comment_parts.append(f"    <body>{comment.body}</body>")
                comment_parts.append("  </comment>")
                parts.append("\n".join(comment_parts))
                comments_included += 1
                comments_total_chars += len(comment.body)
            parts.append("</top_comments>")

        parts.append("</reddit_post>")
        return "\n".join(parts)

    def _build_compact_text(
        self,
        *,
        item: RedditPost,
        link_content: ExtractedContent | None,
    ) -> str:
        parts = self._build_post_metadata(item)

        if not item.image_urls and link_content and getattr(link_content, "images", None):
            parts.append("<images>")
            for img_url in link_content.images:
                parts.append(f"  <image_url>{img_url}</image_url>")
            parts.append("</images>")

        if link_content and getattr(link_content, "text", None):
            parts.append("<linked_article>")
            title = getattr(link_content, "title", None)
            if title:
                parts.append(f"  <article_title>{title}</article_title>")
            description = getattr(link_content, "description", None)
            if description:
                parts.append(f"  <article_description>{description}</article_description>")
            parts.append(f"  <article_body>{link_content.text}</article_body>")
            parts.append("</linked_article>")
        elif link_content and getattr(link_content, "description", None):
            parts.append(f"<article_description>{link_content.description}</article_description>")

        parts.append("</reddit_post>")
        return "\n".join(parts)
