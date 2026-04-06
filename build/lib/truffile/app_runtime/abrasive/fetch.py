import requests
# wrappers around requests to fetch JSON or text from URLs
# can include any anti-detection headers, timeouts, error handling, etc. common here 

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"


def _fetch(url: str, timeout: int = 10) -> requests.Response | None:
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Connection": "close",
            },
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp
    except Exception as e:
        print("Error fetching URL:", url)
        print(e)
        return None

def fetch_json(url: str, timeout: int = 10) -> dict | None:
    resp = _fetch(url, timeout=timeout)
    if resp is None:
        return None
    try:
        return resp.json()
    except Exception as e:
        print("Error parsing JSON from URL:", url)
        print(e)
        return None
    
def fetch_html(url: str, timeout: int = 10) -> str | None:
    resp = _fetch(url, timeout=timeout)
    if resp is None:
        return None
    try:
        return resp.text
    except Exception as e:
        print("Error reading text from URL:", url)
        print(e)
        return None
def fetch_text(url: str, timeout: int = 10) -> str | None:
    return fetch_html(url, timeout=timeout)