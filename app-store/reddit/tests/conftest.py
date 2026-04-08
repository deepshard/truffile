import sys
from pathlib import Path
import types


# add app dir to sys.path for local imports
_app_dir = Path(__file__).resolve().parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

def install_stub_modules() -> None:
    if "app_runtime.abrasive.extract" not in sys.modules:
        extract_mod = types.ModuleType("app_runtime.abrasive.extract")

        class ExtractedContent:
            def __init__(
                self,
                *,
                text: str = "",
                title: str | None = None,
                date: str | None = None,
                source_name: str | None = None,
                source_url: str | None = None,
                images: list[str] | None = None,
            ) -> None:
                self.text = text
                self.title = title
                self.date = date
                self.source_name = source_name
                self.source_url = source_url
                self.images = images or []

        def extract_content_from_url(_url: str) -> ExtractedContent:
            return ExtractedContent()

        extract_mod.ExtractedContent = ExtractedContent
        extract_mod.extract_content_from_url = extract_content_from_url
        sys.modules["app_runtime.abrasive.extract"] = extract_mod

    if "app_runtime.abrasive.fetch" not in sys.modules:
        fetch_mod = types.ModuleType("app_runtime.abrasive.fetch")
        fetch_mod.USER_AGENT = "app-store-reddit-test"
        sys.modules["app_runtime.abrasive.fetch"] = fetch_mod

    import requests

    if not getattr(requests, "_reddit_test_stub_installed", False):
        class _FakeResponse:
            def __init__(self, payload: object) -> None:
                self._payload = payload

            def json(self) -> object:
                return self._payload

            def raise_for_status(self) -> None:
                return None

        def _fake_requests_get(
            url: str,
            *,
            params: dict[str, object] | None = None,
            headers: dict[str, str] | None = None,
            timeout: int = 10,
        ) -> _FakeResponse:
            del params, headers, timeout
            if "/comments/" in url:
                return _FakeResponse(
                    [
                        {"data": {"children": []}},
                        {
                            "data": {
                                "children": [
                                    {
                                        "kind": "t1",
                                        "data": {
                                            "id": "c1",
                                            "author": "alice",
                                            "body": "Interesting thread context.",
                                            "score": 101,
                                            "permalink": "/r/news/comments/test/c1/",
                                        },
                                    }
                                ]
                            }
                        },
                    ]
                )
            return _FakeResponse(
                {
                    "data": {
                        "after": None,
                        "children": [
                            {
                                "kind": "t3",
                                "data": {
                                    "name": "t3_test123",
                                    "id": "test123",
                                    "title": "Stubbed Reddit post",
                                    "subreddit": "news",
                                    "permalink": "/r/news/comments/test123/stubbed_reddit_post/",
                                    "url": "https://example.com/story",
                                    "score": 123,
                                    "num_comments": 5,
                                    "created_utc": 1710000000,
                                    "domain": "example.com",
                                    "thumbnail": "https://example.com/thumb.png",
                                },
                            }
                        ],
                    }
                }
            )

        requests.get = _fake_requests_get
        requests._reddit_test_stub_installed = True


install_stub_modules()
