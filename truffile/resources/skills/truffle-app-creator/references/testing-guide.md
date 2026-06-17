# Testing Guide

## Unit Tests

Every app needs tests that run without network, auth, or a device.

```python
from truffile.app_runtime import FakeApiKeyProvider, FakeHttpResponse, FakeHttpTransport, AppHarness

class TestMyClient(unittest.IsolatedAsyncioTestCase):
    async def test_search_returns_results(self):
        transport = FakeHttpTransport({
            "GET /search": FakeHttpResponse(200, _json={"results": [{"id": 1}]})
        })
        auth = FakeApiKeyProvider(authenticated=True)
        client = MyClient(auth=auth, http=transport)
        results = await client.search("test")
        self.assertEqual(len(results), 1)
```

## App Shell Tests

Test tool invocation through AppHarness:

```python
class TestMyAppShells(unittest.IsolatedAsyncioTestCase):
    async def test_foreground_tool(self):
        harness = AppHarness(fg_app=my_app)
        with patch("my_client.search", return_value=[{"id": 1}]):
            result = await harness.run_fg(calls=[("search", {"query": "test"})])
        self.assertTrue(result.success)

    async def test_background_submission(self):
        harness = AppHarness(bg_app=my_bg_app)
        with patch.object(my_bg_app, "run_cycle", return_value=mock_result):
            result = await harness.run_bg(cycles=1)
        self.assertGreater(len(result.submissions), 0)
```

## What to Test

- parsing and formatting (all pure functions)
- client request construction and response handling
- background worker dedup and state management
- error paths (401, 403, timeouts)
- config loading and validation

## Test File Structure

```
tests/
├── conftest.py              # sys.path setup
├── test_<app>_unit.py       # business logic with fakes
└── test_<app>_app_shells.py # FG/BG through AppHarness
```
