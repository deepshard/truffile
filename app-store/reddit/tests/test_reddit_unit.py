from __future__ import annotations

import tempfile
import unittest
from unittest.mock import MagicMock, patch

from reddit_bg_worker import RedditBackgroundWorker
from reddit_common import RedditComment, RedditConfig, RedditPost, normalize_user_feed_url, parse_subreddits

class TestRedditUnit(unittest.TestCase):
    def _make_worker(self) -> RedditBackgroundWorker:
        return RedditBackgroundWorker(
            config=RedditConfig(subreddits=["news"], user_feed_url=None),
        )

    def _make_post(self, **overrides: object) -> RedditPost:
        defaults: dict[str, object] = dict(
            fullname="t3_abc123",
            id="abc123",
            title="Big policy story",
            subreddit="news",
            permalink="/r/news/comments/abc123/big_policy_story/",
            comments_url="https://www.reddit.com/r/news/comments/abc123/big_policy_story/",
            article_url="https://example.com/story",
            image_urls=["https://example.com/cover.png"],
            score=420,
            num_comments=37,
            created_utc=__import__("datetime").datetime.now(__import__("datetime").UTC),
            domain="example.com",
        )
        defaults.update(overrides)
        return RedditPost(**defaults)

    def test_parse_subreddits_dedupes_and_preserves_order(self) -> None:
        self.assertEqual(
            parse_subreddits("news, worldnews, news, technology,  "),
            ["news", "worldnews", "technology"],
        )

    def test_normalize_user_feed_url_rewrites_rss_and_adds_sort(self) -> None:
        raw = "https://old.reddit.com/.rss?feed=abcd1234&user=tester"
        self.assertEqual(
            normalize_user_feed_url(raw),
            "https://old.reddit.com/hot/.json?feed=abcd1234&user=tester",
        )

    def test_verify_rejects_invalid_config(self) -> None:
        worker = self._make_worker()
        with patch.object(worker, "reddit_request", side_effect=RuntimeError("bad request")):
            ok, message = worker.verify()

        self.assertFalse(ok)
        self.assertIn("invalid", message.lower())

    def test_prepare_submission_includes_metadata_article_and_comments(self) -> None:
        worker = self._make_worker()
        post = self._make_post()
        extracted = MagicMock(
            text="Long-form article text.",
            title="Policy story",
            date="2026-03-22",
            source_name="Example",
            source_url="https://example.com/story",
        )
        comments = [
            RedditComment(
                id="c1",
                author="alice",
                body="Interesting context from the thread.",
                score=99,
                permalink="https://reddit.com/c1",
            )
        ]

        with patch.object(worker, "get_content_for_reddit_item", return_value=(extracted, comments)):
            submission = worker.prepare_submission(post)

        self.assertIn("Policy story", submission.text)
        self.assertIn("Interesting context from the thread.", submission.text)
        self.assertIn("https://example.com/story", submission.uris)

    def test_extract_image_urls_from_preview(self) -> None:
        worker = self._make_worker()
        post_data = {
            "preview": {
                "images": [
                    {"source": {"url": "https://i.redd.it/img1.jpg&amp;w=600"}},
                    {"source": {"url": "https://i.redd.it/img2.png"}},
                ]
            }
        }
        urls = worker._extract_image_urls(post_data)
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls[0], "https://i.redd.it/img1.jpg&w=600")
        self.assertEqual(urls[1], "https://i.redd.it/img2.png")

    def test_extract_image_urls_missing_preview(self) -> None:
        worker = self._make_worker()
        urls = worker._extract_image_urls({})
        self.assertEqual(urls, [])

    def test_xml_submission_has_all_tags(self) -> None:
        worker = self._make_worker()
        post = self._make_post()
        extracted = MagicMock(
            text="Article body text here.",
            title="Article Title",
            date=None,
            source_name=None,
            source_url=None,
        )
        comments = [
            RedditComment(id="c1", author="bob", body="Great post!", score=50, permalink=""),
        ]
        text = worker._build_full_text(item=post, link_content=extracted, comments=comments)
        self.assertIn("<subreddit>news</subreddit>", text)
        self.assertIn("<title>Big policy story</title>", text)
        self.assertIn("<linked_article>", text)
        self.assertIn("<top_comments>", text)

    def test_seen_set_dedup(self) -> None:
        worker = self._make_worker()
        post = self._make_post(fullname="t3_dup1")
        item = worker._pending_reddit
        item.append(post)
        first = worker._next_new_reddit_item()
        self.assertIsNotNone(first)
        self.assertIn("t3_dup1", worker._seen_reddit)
        worker._enqueue_unseen([post], source="test_after_seen")
        self.assertEqual(len(worker._pending_reddit), 0)

    def test_normalize_feed_url_adds_sort(self) -> None:
        raw = "https://www.reddit.com/.json?feed=abc123&user=tester"
        result = normalize_user_feed_url(raw, sort="new")
        self.assertIsNotNone(result)
        self.assertIn("/new/", result)
        self.assertIn(".json?feed=", result)

if __name__ == "__main__":
    unittest.main()
