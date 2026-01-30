from gourmet.ambient import run_ambient, AmbientContext, InferenceClient

from abrasive.extract import extract_content_from_url, ExtractedContent
from abrasive.fetch import USER_AGENT
from typing import Deque, List, Optional, Tuple, Any
from collections import deque
import logging
import requests
from dataclasses import dataclass
import logging
import time
import os
from datetime import datetime
from datetime import UTC
logger = logging.getLogger("reddit")
logger.setLevel(logging.DEBUG)

REDDIT_JSON_REQUESTS_PER_MINUTE = 10
REDDIT_JSON_RATE_LIMIT_SECONDS = 60 / REDDIT_JSON_REQUESTS_PER_MINUTE

DEFAULT_SUBREDDITS = ["news", "worldnews", "all"]
SORT = "hot"   # "hot", "new", "top", ...
POST_LIMIT = 32

@dataclass 
class RedditConfig:
    subreddits: List[str]
    user_feed_url: Optional[str]
    sort : str = SORT
    post_limit : int = POST_LIMIT

    def get_listing_url(self) -> str:
        if self.user_feed_url:
            return self.user_feed_url
        else:
            return f"https://www.reddit.com/r/{'+'.join(self.subreddits)}/{self.sort}/.json"
        
    @staticmethod
    def load_reddit_config_from_env() -> "RedditConfig":
        subreddits_str = os.getenv("SUBREDDITS", "").strip()
        user_feed_url = os.getenv("USER_FEED_URL", "").strip()

        subreddits: List[str] = []

        # user may have done comma space or just comma
        if subreddits_str:
            subreddits = [s.strip() for s in subreddits_str.split(",") if s.strip()]
        else:
            subreddits = DEFAULT_SUBREDDITS

        if user_feed_url:
            assert isinstance(user_feed_url, str)
            # validate url format minimally
            if not ( user_feed_url.startswith("http://") or user_feed_url.startswith("https://")):
                logger.warning("Invalid USER_FEED_URL format, ignoring: %s", user_feed_url)
                user_feed_url = None
            elif not "reddit.com" in user_feed_url:
                logger.warning("USER_FEED_URL does not appear to be a reddit.com url, ignoring: %s", user_feed_url)
                user_feed_url = None
            if user_feed_url and  ".rss" in user_feed_url:
                logger.warning("USER_FEED_URL appears to be an RSS feed, expected JSON feed, replacing: %s", user_feed_url)
                user_feed_url = user_feed_url.replace(".rss", ".json")

            if user_feed_url and not ".json?feed=" in user_feed_url:
                logger.warning("USER_FEED_URL does not appear to be a reddit JSON feed url, ignoring: %s", user_feed_url)
                user_feed_url = None
            elif user_feed_url and not "user=" in user_feed_url:
                logger.warning("USER_FEED_URL does not appear to be a user frontpage feed url, ignoring: %s", user_feed_url)
                user_feed_url = None
        
        if user_feed_url:
            # add sort 
            # https://old.reddit.com/.json?feed=uuid1234ffffaaaa&user=bobnal&sort=new
            dotjson_index = user_feed_url.find("/.json")
            if dotjson_index != -1:
                user_feed_url = f"{user_feed_url[:dotjson_index]}/{SORT}{user_feed_url[dotjson_index:]}"
            else:
                logger.warning("Could not find /.json in USER_FEED_URL, could not add sort!", user_feed_url)

        return RedditConfig(
            subreddits=subreddits,
            user_feed_url=user_feed_url
        )

reddit_config = RedditConfig.load_reddit_config_from_env()



@dataclass
class RedditPost:
    fullname: str           # "t3_xxx"
    id: str                 # bare id, e.g. "1pczt9f"
    title: str
    subreddit: str
    permalink: str          # "/r/.../comments/..."
    comments_url: str       # "https://www.reddit.com" + permalink
    article_url: str        # external link or self post url
    image_urls: Optional[List[str]]
    score: int
    num_comments: int
    created_utc: datetime
    domain: str

@dataclass
class RedditComment:
    id: str
    author: Optional[str]
    body: str               # markdown text
    score: Optional[int]
    permalink: str

_seen_reddit: set[str] = set()
_pending_reddit: Deque[RedditPost] = deque()
_listing_after: Optional[str] = None
_listing_after_fp: Optional[str] = None

last_request_time = time.time() - REDDIT_JSON_RATE_LIMIT_SECONDS
def reddit_request(url: str, params: dict, timeout: int = 10) -> requests.Response:
    global last_request_time
    elapsed = time.time() - last_request_time
    if elapsed < REDDIT_JSON_RATE_LIMIT_SECONDS:
        time.sleep((REDDIT_JSON_RATE_LIMIT_SECONDS - elapsed) + 0.25 )
    last_request_time = time.time()
    headers = {
        "User-Agent": USER_AGENT,
        "Connection": "close",
    }
    logger.warning("Reddit JSON request to %s with params %s", url, params)
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp

def _fetch_listing(after: Optional[str] = None) -> Tuple[List[RedditPost], Optional[str]]:
    params : dict[str, Any]= {"limit": POST_LIMIT, "sort" : "new"}
    if after:
        params["after"] = after
    global reddit_config

    resp = reddit_request(reddit_config.get_listing_url(), params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()["data"]
    children = data.get("children", [])
    after_token = data.get("after")

    posts: List[RedditPost] = []
    for child in children:
        if child.get("kind") != "t3":
            continue
        d : dict[str, Any] = child["data"]

        fullname = d.get("name")
        if not fullname:
            continue

        permalink = d.get("permalink") or ""
        comments_url = f"https://www.reddit.com{permalink}" if permalink else ""

        article_url = d.get("url_overridden_by_dest") or d.get("url") or ""

        # get best image 
        image_urls: List[str]= []
        if 'preview' in d and 'images' in d['preview'] and len(d['preview']['images']) > 0:
            for img in d['preview']['images']:
                if 'source' in img and 'url' in img['source']:
                    image_urls.append(img['source']['url'].replace("&amp;", "&"))
                
        if not image_urls:
            thumb = d.get("thumbnail")
            if thumb and thumb.startswith("http"):
                image_urls.append(thumb.replace("&amp;", "&"))


        created_float = float(d.get("created_utc") or 0.0)
        created_utc = datetime.fromtimestamp(created_float, tz=UTC) if created_float > 0.0 else datetime.now()
        posts.append(
            RedditPost(
                fullname=fullname,
                id=d.get("id", ""),
                title=d.get("title", ""),
                subreddit=d.get("subreddit", ""),
                permalink=permalink,
                comments_url=comments_url,
                article_url=article_url,
                image_urls=image_urls if image_urls else None,
                score=int(d.get("score") or 0),
                num_comments=int(d.get("num_comments") or 0),
                created_utc=created_utc,
                domain=d.get("domain", ""),
            )
        )

    return posts, after_token


def _refill_from_frontpage() -> bool:
    global _listing_after_fp
    posts, after_token = _fetch_listing(after=None)
    _listing_after_fp = after_token

    added = 0
    for p in posts:
        if p.fullname in _seen_reddit:
            continue
        _pending_reddit.append(p)
        added += 1

    logger.debug("frontpage refill added %d posts", added)
    return added > 0


def _refill_from_older() -> bool:
    global _listing_after
    # if not _listing_after:
    #     return False

    posts, after_token = _fetch_listing(after=_listing_after)
    _listing_after = after_token

    added = 0
    for p in posts:
        if p.fullname in _seen_reddit:
            continue
        _pending_reddit.append(p)
        added += 1

    logger.debug("older-page refill added %d posts (after=%s)", added, _listing_after)
    return added > 0


def _refill_reddit():
    if _refill_from_frontpage():
        return
    _refill_from_older()


def _next_new_reddit_item() -> Optional[RedditPost]:
    global _pending_reddit, _seen_reddit

    if not _pending_reddit:
        _refill_reddit()

    if not _pending_reddit:
        return None

    item = _pending_reddit.popleft()
    _seen_reddit.add(item.fullname)
    return item


def fetch_post_comments(
    post: RedditPost,
    max_top: int = 10,
) -> List[RedditComment]:
    if not post.permalink:
        return []

    url = f"https://www.reddit.com{post.permalink.rstrip('/')}.json"
    resp = reddit_request(url, params={"sort": "top", "limit": 50}, timeout=10)
    resp.raise_for_status()
    blob = resp.json()

    if not isinstance(blob, list) or len(blob) < 2:
        return []

    comments_listing = blob[1]["data"]["children"]

    raw: List[RedditComment] = []
    for child in comments_listing:
        if child.get("kind") != "t1":
            continue
        d = child["data"]
        body = d.get("body")
        if not body:
            continue

        permalink = d.get("permalink") or ""
        raw.append(
            RedditComment(
                id=d.get("id", ""),
                author=d.get("author"),
                body=body,
                score=d.get("score"),
                permalink=f"https://www.reddit.com{permalink}" if permalink else "",
            )
        )

    if not raw:
        return []

    raw.sort(key=lambda c: (c.score or 0), reverse=True)
    top = raw[:max_top]

    # maybe merit to adding worst comments too? if downvoted
    worst = min(raw, key=lambda c: (c.score or 0))
    if worst not in top and len(top) < max_top + 1:
        top.append(worst)

    return top


def get_content_for_reddit_item(
    item: RedditPost,
) -> Tuple[ExtractedContent | None, List[RedditComment]]:
    try:
        link_content = None
        if item.article_url and not item.domain.startswith("self."):
            link_content = extract_content_from_url(item.article_url)
        comments = fetch_post_comments(item, max_top=10)
        return link_content, comments
    except Exception as e:
        logger.error("Error fetching content for %s: %s", item.fullname, e, exc_info=True)
        return None, []

def validate_reddit_config(config: RedditConfig) -> bool:
    try:
        url = config.get_listing_url()
        resp = reddit_request(url, params={"limit": 1}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "data" not in data:
            logger.error("Reddit config validation failed: no 'data' in response")
            return False
        return True
    except Exception as e:
        logger.error("Reddit config validation error: %s", e, exc_info=True)
        return False

def test_once():
    item = _next_new_reddit_item()
    if item is None:
        print("No new reddit items.")
        return

    logger.info(
        "Processing Reddit post %s [%s] %s (%s) score=%d comments=%d imgs=[%s]",
        item.fullname,
        item.subreddit,
        item.title,
        item.article_url,
        item.score,
        item.num_comments,
        " ".join(item.image_urls) if item.image_urls else "None",
    )
    post, comments = get_content_for_reddit_item(item)
    print("Post:", item.title)
    print("Article URL:", item.article_url)
    print("Comments fetched:", len(comments))
    print("thumb:", item.image_urls or "None")
    print("Top comments:")
    for c in comments[:3]:
        print(f"- @{c.author} [{c.score}]: {c.body[:160].replace('\n', ' ')}...")
    print("Article text:", post.text[:500].replace("\n", " ") if post and post.text else "None")
    print("article images:", post.images[0] if post and len(post.images) else "None")
    print("-----")

TESTING_MODE = False

def run_test():
    global reddit_config

    logger.info("Starting reddit JSON ambient test...")
    logger.info("using reddit listing url: %s", reddit_config.get_listing_url())
    

    while True:
        try:
            test_once()
            time.sleep(5)
        except KeyboardInterrupt:
            print("Exiting.")
            break

def process_reddit_item(ctx: AmbientContext, item: RedditPost):
    title, url, item_id, subreddit, image_urls = (
        item.title,
        item.article_url,
        item.fullname,
        item.subreddit,
        item.image_urls,
    )
    logger.info(f"Processing Reddit item {item_id}: {title} ({url}) {subreddit if subreddit else ''} {image_urls if image_urls else ''}")
    link_content, comments = get_content_for_reddit_item(item)
    ctx.bg.post_to_feed(
        title=link_content.title if link_content and link_content.title else title,
        body=link_content.text if link_content and link_content.text else f'**{subreddit}** {item.domain} {item.score}',
        src_uri=url,
        media_uris=link_content.images if link_content and link_content.images else (image_urls if image_urls else []),
        content_timestamp = link_content.date if link_content and link_content.date else item.created_utc
    )

def reddit_ambient(ctx: AmbientContext):
    for _ in range(3):
        item = _next_new_reddit_item()
        if not item:
            logger.info("No new reddit items to process.")
            return
        process_reddit_item(ctx, item)
    
    return 
    

    #post_body = f"{f'**{subreddit}**' if subreddit else ''} {item.score }\n"
    # 

    # if link_content and link_content.text:
    #     post_body += f"\n\n{link_content.text[:2000]}"

    # if comments:
    #     post_body += "\n\n**Top Comments:**\n"
    #     for c in comments:
    #         post_body += f"- @{c.author if c.author else 'unknown'}: {c.body[:300].replace('\n', ' ')}...\n"




if __name__ == "__main__":
    import sys 
    if sys.argv and len(sys.argv) > 1 and sys.argv[1] and "verify" in sys.argv[1].lower():
        logger.info("Verifying reddit configuration...")
        ok = validate_reddit_config(reddit_config)
        logger.info("Reddit configuration valid: %s", str(reddit_config)) if ok else logger.error("Reddit configuration invalid!")
        sys.exit(0 if ok else 1)
        
    if TESTING_MODE:
        run_test()
    else:
        run_ambient(reddit_ambient)


# :cp ./apps/ambient/reddit.py /app.py
# :cp /home/dylan/ds/3fw/python/dist/gourmet-0.1.dev0-py3-none-any.whl /tmp/gourmet-0.1.dev0-py3-none-any.whl
# pip install /tmp/gourmet-0.1.dev0-py3-none-any.whl[abrasive]