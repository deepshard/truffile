import time
import random
import os 
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webelement import WebElement
from gourmet.ambient import AmbientContext, run_ambient
from gourmet.desktop.xvfb import start_xvfb
from gourmet.desktop.chromedriver import create_driver, human_sleep, human_scroll

from dataclasses import dataclass
from typing import Optional
import re 
import subprocess
import pathlib
import logging
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@dataclass
class Tweet:
    author_name: Optional[str]
    author_handle: Optional[str]
    text: str
    url: Optional[str]
    num_replies: Optional[int]
    reposts: Optional[int]
    likes: Optional[int]
    bookmarks: Optional[int]
    views: Optional[int]
    images: Optional[list[str]] = None  # URLs to images

def tweet_to_string(tweet: Tweet) -> str:
    s = (
        f"{tweet.author_handle} ({tweet.url})\n"
        f"{tweet.text}\n"
        f"QT: {tweet.num_replies}, RTS: {tweet.reposts}, "
        f"<3: {tweet.likes}, Saves: {tweet.bookmarks}, Views: {tweet.views}\n"
    )
    return s
_stats_re = re.compile(
    r"(?P<replies>[\d,]+)\s+replies?,\s+"
    r"(?P<reposts>[\d,]+)\s+reposts?,\s+"
    r"(?P<likes>[\d,]+)\s+likes?,\s+"
    r"(?P<bookmarks>[\d,]+)\s+bookmarks?,\s+"
    r"(?P<views>[\d,]+)\s+views?",
    re.I,
)

def _parse_int(s: str) -> int:
    return int(s.replace(",", ""))

def parse_stats(aria_label: str):
    m = _stats_re.search(aria_label or "")
    if not m:
        return (None, None, None, None, None)
    return tuple(
        _parse_int(m.group(k)) for k in
        ["replies", "reposts", "likes", "bookmarks", "views"]
    )
def _normalize_twitter_media_url(url: str, *, name: str = "orig") -> str:
    # https://pbs.twimg.com/media/<id>?format=jpg&name=small  -> name=orig
    try:
        u = urlparse(url)
        q = parse_qs(u.query)
        if "name" in q:
            q["name"] = [name]
        # keep format if present; don't invent it
        query = urlencode({k: v[0] for k, v in q.items()}, doseq=False)
        return urlunparse((u.scheme, u.netloc, u.path, u.params, query, u.fragment))
    except Exception:
        return url

def extract_tweet_images(article) -> list[str]:
    urls: list[str] = []

    # Primary: tweetPhoto blocks
    for img in article.find_elements(By.CSS_SELECTOR, "div[data-testid='tweetPhoto'] img"):
        src = (img.get_attribute("src") or "").strip()
        if not src:
            continue
        urls.append(_normalize_twitter_media_url(src))

    # Fallback: sometimes media shows up as <img src="...pbs.twimg.com/media/...">
    # chatgpt did this shit but idk if we should guard on not urls tbh 
    if not urls:
        for img in article.find_elements(By.CSS_SELECTOR, "img[src*='pbs.twimg.com/media/']"):
            src = (img.get_attribute("src") or "").strip()
            if src:
                urls.append(_normalize_twitter_media_url(src))

    deduped: list[str] = []
    seen = set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped

def extract_tweet(article) -> Tweet:
    # main text
    try:
        text_el = article.find_element(
            By.CSS_SELECTOR, "div[data-testid='tweetText']"
        )
        text = text_el.text
    except Exception:
        text = ""

    # author block via data-testid=User-Name
    author_name = None
    author_handle = None
    try:
        user_block = article.find_element(
            By.CSS_SELECTOR, "div[data-testid='User-Name']"
        )
        spans = user_block.find_elements(By.CSS_SELECTOR, "span")
        for s in spans:
            t = s.text.strip()
            if not t:
                continue
            if t.startswith("@") and author_handle is None:
                author_handle = t
            elif author_name is None:
                author_name = t
    except Exception:
        pass

    replies = reposts = likes = bookmarks = views = None
    try:
        stats_group = article.find_element(
            By.CSS_SELECTOR,
            "div[role='group'][aria-label*='replies'][aria-label*='views']"
        )
        aria = stats_group.get_attribute("aria-label") or ""
        replies, reposts, likes, bookmarks, views = parse_stats(aria)
    except Exception:
        pass

    url = None
    try:
        link = article.find_element(
            By.CSS_SELECTOR, "a[role='link'][href*='/status/']"
        )
        href = link.get_attribute("href")
        if href:
            url = href.split("/analytics")[0]
    except Exception:
        pass
    images: list[str] | None = None
    try:
        imgs = extract_tweet_images(article)
        if imgs:
            images = imgs
    except Exception:
        pass

    return Tweet(
        author_name=author_name,
        author_handle=author_handle,
        text=text,
        url=url,
        num_replies=replies,
        reposts=reposts,
        likes=likes,
        bookmarks=bookmarks,
        views=views,
        images=images,
    )



def collect_tweets_on_screen(driver, max_items=50):
    articles = driver.find_elements(
        By.CSS_SELECTOR, "article[data-testid='tweet']"
    )
    tweets = []
    seen_urls = set()

    for a in articles:
        t = extract_tweet(a)
        key = t.url or (t.author_handle, t.text)
        if key in seen_urls:
            continue
        seen_urls.add(key)
        tweets.append(t)
        if len(tweets) >= max_items:
            break

    return tweets
DEBUG_SS_DIR = pathlib.Path("/opt/tfw_x_debug_screenshots")
DEBUG_SS_DIR.mkdir(parents=True, exist_ok=True)
def save_debug_screenshot(driver : uc.Chrome | None, name: str = "screenshot") -> None:
    if driver is None:
        logger.warning("Cannot save debug screenshot: driver is None")
        return
    timestamp = int(time.time())
    ss_path = DEBUG_SS_DIR / f"{name}_{timestamp}.png"
    if not driver.save_screenshot(str(ss_path.absolute())):
        logger.error("Failed to save debug screenshot")
        return
    logger.info(f"Saved debug screenshot to {ss_path.absolute()}")

seen_urls = set()
def scroll_feed_and_scrape(driver, num_tweets, batch_limit=30) -> list[Tweet]:
    all_tweets = []
    global seen_urls
    MAX_TIME = 200  # seconds
    start_time = time.time()
    it = 0
    while len(all_tweets) < num_tweets:
        if (time.time() - start_time) > MAX_TIME:
            logger.error(f"Timeout while scrolling feed after {MAX_TIME} seconds- only got {len(all_tweets)} tweets")
            save_debug_screenshot(driver, name=f"scroll_timeout_{len(all_tweets)}tweets")
            break
        # scrape what we currently see
        batch = collect_tweets_on_screen(driver, max_items=batch_limit)
        new_tweets = []
        for tweet in batch:
            key = tweet.url or (tweet.author_handle, tweet.text)
            if key in seen_urls:
                scroll_amount = random.randint(700, 1300)
                driver.execute_script(
                    "window.scrollBy(0, arguments[0]);", scroll_amount
                )
                human_sleep(0.5, 1.6)
                continue
            seen_urls.add(key)
            new_tweets.append(tweet)
            print(tweet_to_string(tweet))
        all_tweets.extend(new_tweets)
        

        logger.debug(f"\n[iteration: {it}] collected {len(new_tweets)} unique tweets so far")
        it += 1
        # human-ish scrolling
        scroll_amount = random.randint(700, 1300)
        driver.execute_script(
            "window.scrollBy(0, arguments[0]);", scroll_amount
        )
        human_sleep(1.0, 2.3)



    return all_tweets


DEFAULT_NUM_TWEETS_TO_SCRAPE = 30
def scrape_tweets(num_tweets : int = DEFAULT_NUM_TWEETS_TO_SCRAPE ) -> list[Tweet]:
    tweets = []
    driver = None
    try:
        logger.info(f"Creating ChromeDriver to scrape {num_tweets} tweets from X")
        driver = create_driver()
        logger.info("Navigating to X home feed")
        driver.get("https://x.com/home")
        logger.info("Waiting for X home feed to load")
        human_sleep(2, 6)
        logger.info("Starting to scroll feed and scrape tweets")
        tweets = scroll_feed_and_scrape(driver, num_tweets=num_tweets, batch_limit=40)

        logger.info(f"Scraped a total of {len(tweets)} unique tweets.")

        human_sleep(1, 3)
        if not tweets:
            logger.warning("No tweets were scraped from X feed.")
            save_debug_screenshot(driver, name="no_tweets_scraped")
        
    except Exception as e:
        logger.error("Error during X scraping", exc_info=True)
        print(f"Error during X scraping: {e!r}")
        save_debug_screenshot(driver, name="error_scrape")
    finally:
        if driver is not None:
            logger.info("Quitting ChromeDriver")
            driver.quit()
    return tweets

def x_ambient_app(ctx: AmbientContext):
    logger.info("Running X Ambient App")
    tweets = scrape_tweets(10)
    if not tweets:
        logger.info("No tweets scraped.")
        return
    logger.warning(f"got back{len(tweets)} tweets from X feed.")
    for tweet in tweets:
        body = f"{tweet.text}\n\n {tweet.likes} Likes, {tweet.reposts} Reposts, {tweet.num_replies} Replies, {tweet.views} Views"
        src = tweet.url or "https://x.com"
        title = tweet.author_handle or "Tweet"
        media_uris = tweet.images if tweet.images else []
        ctx.bg.post_to_feed(title=title, body=body, src_uri=src, media_uris=media_uris)
    logger.debug("Finished posting tweets to feed.")


def test():
    print("Running X Ambient App TEST")
    tweets = scrape_tweets(10)
    if not tweets:
        print("No tweets scraped.")
        return
    print(f"Scraped {len(tweets)} tweets from X feed.")
    for tweet in tweets:
        body = f"{tweet.text}\n\n {tweet.likes} Likes, {tweet.reposts} Reposts, {tweet.num_replies} Replies, {tweet.views} Views"
        src = tweet.url or "https://x.com"
        title = tweet.author_handle or "Tweet"
        print(f"Posting to feed: {title}\n{body}\nSource: {src}\n")
    print("Finished posting tweets to feed.")

if __name__ == "__main__":
    logger.info("Starting Xvfb for ChromeDriver App")
    import asyncio
    asyncio.run(start_xvfb())
    logger.info("Xvfb is ready")
    time.sleep(1) # socket file exists, still might need a sec  
    
    run_ambient(x_ambient_app)


"""
:cp ./apps/chrome/chromedriver_app.py app.py
:cp ./apps/chrome/chromedriver.py chromedriver.py 
:cp ./apps/chrome/setup.sh setup.sh
:cp ./apps/chrome/xvfb_vnc.sh xvfb_vnc.sh
chmod +x setup.sh
chmod +x xvfb_vnc.sh
./setup.sh
http://localhost:80/containers/edb88273-c414-4b48-9a14-682317018cd6
http://localhost:80/containers/dc33ce5b-f37b-4d65-a803-c7db4e045cb7
"""