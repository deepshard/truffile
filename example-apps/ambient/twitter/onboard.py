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

from gourmet.desktop.chromedriver import create_driver, human_sleep, human_scroll

from dataclasses import dataclass
from typing import Optional
import asyncio
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
async def wait_for_login(driver, timeout_s: int = 900, poll_s: float = 0.2) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s

    def logged_in() -> bool:
        url = driver.current_url or ""
        if "/home" in url and "x.com" in url:
            return True
        try:
            return any(c.get("name") == "auth_token" for c in driver.get_cookies())
        except Exception:
            return False

    while True:
        if logged_in():
            return
        if loop.time() >= deadline:
            raise TimeoutError("Timed out waiting for user to log in")
        await asyncio.sleep(poll_s)


async def main() -> int:
    err = 0
    try:
        driver = create_driver(
            app_url="https://x.com",
            fullscreen=True
        )
        driver.get("https://x.com/")
        logger.info("Waiting for user to log in to Twitter/X")
        logger.error("Please log in to Twitter/X in the opened browser window")
        await wait_for_login(driver, timeout_s=900)
        logger.info("Logged in to Twitter/X successfully")
        await asyncio.sleep(0.2) #dont need this
        driver.quit()
        driver = None
        err = 0
    except Exception as e:
        logger.exception("Error during Twitter/X onboarding")
        err = 1
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
    return err



if __name__ == "__main__":
    ec = asyncio.run(main())
    exit(ec)