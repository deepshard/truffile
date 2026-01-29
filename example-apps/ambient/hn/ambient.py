from gourmet.ambient import run_ambient, AmbientContext, InferenceClient
from truffle.app.background_feed_pb2 import FeedCard
import logging
import requests
from bs4 import BeautifulSoup
from bs4 import Tag
from typing import Deque, Tuple, Optional
from collections import deque
from urllib.parse import urljoin
from abrasive.extract import extract_content_from_url, ExtractedContent
import datetime
logger = logging.getLogger("hn")
logger.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# pip install requests bs4 
def summarize_post_title(infer_client: InferenceClient, title: str) -> str:
    sys_prompt = ( "You summarize updates from a Hacker News front page scraper, to make a catchy post title."
                  " Only respond with the title text, no other commentary." )
    user_prompt = "What is a catchy headline for the following article?\n\n" + title
    response = infer_client.generate_simple(sys_prompt, user_prompt)
    return response.strip()
HN_URL = "https://news.ycombinator.com/"

_seen_ids: set[str] = set()
_pending: Deque[Tuple[str, str, Optional[str],Optional[str], str]] = deque()  # (title, url, site, item_id)


def _get(url: str) -> str:
    r = requests.get(
        url,
        headers={
            "User-Agent": "hn-scraper/1.0 (+https://news.ycombinator.com/)",
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.text


def _fetch_top(limit: int = 60) -> list[Tuple[str, str, Optional[str],Optional[str], str]]:
    html = _get(HN_URL)
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr.athing")

    out: list[Tuple[str, str, Optional[str],Optional[str], str]] = []
    for r in rows:
        item_id = r.get("id")
        if not item_id:
            continue
        a = r.select_one("span.titleline > a")
        
        if not a:
            continue
        href = urljoin(HN_URL, a.get("href") or "") # type: ignore
        title = a.get_text(strip=True)
        site_el = r.select_one("span.sitestr")

        next = r.next_sibling
        points = None
        if next is not None and isinstance(next, Tag):
            points_el = next.select_one("td.subtext > span.subline > span.score")
            if points_el is not None:
                points = points_el.get_text(strip=True)
                if points.endswith(" points"):
                    points = points[:-7]
        site = site_el.get_text(strip=True) if site_el else None
        out.append((title, href, site, points, item_id)) # type: ignore
        if len(out) >= limit:
            break
    return out


def _refill_queue() -> int:
    global _pending, _seen_ids
    try:
        batch = _fetch_top(limit=60)
    except Exception as e:
        logger.warning(f"HN fetch failed: {e!r}")
        return 0

    added = 0
    existing_ids = {it[4] for it in _pending}
    for it in batch:
        if it[4] in _seen_ids or it[4] in existing_ids:
            continue
        _pending.append(it)
        existing_ids.add(it[4])
        added += 1
    return added
def _next_new_item() -> Optional[Tuple[str, str, Optional[str],Optional[str], str]]:
    global _pending
    if not _pending:
        _refill_queue()
    if not _pending:
        return None
    title, url, site, pts, item_id = _pending.popleft()
    _seen_ids.add(item_id)
    return title, url, site, pts, item_id
def get_comments_url(item_id: str) -> str:
    return f"{HN_URL}item?id={item_id}"
def scrape_ambient(ctx: AmbientContext):
    item = _next_new_item()
    if not item:
        logger.info("No new HN items to process.")
        return
    title, url, site,pts, item_id = item
    logger.info(f"Processing HN item {item_id}: {title} {pts or ""} ({url}) ({site}) {get_comments_url(item_id=item_id)}")
    

    post_body = f"HackerNews: {f'{site}' if site else ''}{f' | {pts} points' if pts is not None else ''}\n"
    url_content = extract_content_from_url(url)
    if url_content is None:
        logger.warning(f"Failed to extract content from URL: {url}")
        post_body += f"[comments]({get_comments_url(item_id=item_id)})\n"
        ctx.bg.post_to_feed(title=title, body=post_body, src_uri=url)
        return
    
    if url_content.text:
        post_body += f"{url_content.text}\n"

    ts = url_content.date if url_content.date is not None else datetime.datetime.now(tz=datetime.timezone.utc)
    ctx.bg.post_to_feed(title=title, body=post_body, src_uri=url, media_uris=url_content.images, content_timestamp=ts )
    
if __name__ == "__main__":
    run_ambient(scrape_ambient)


