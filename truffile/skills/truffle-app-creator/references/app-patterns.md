# App Patterns

## Foreground Only (MCP tools for agent)

```python
from truffile.app_runtime import ForegroundApp, ToolSpec, err, ok

app = ForegroundApp("my-app")

@app.tool(ToolSpec(
    name="search",
    description="Search items.",
    icon="magnifying-glass",
    annotations={"readOnlyHint": True, "destructiveHint": False},
))
async def search(query: str, limit: int = 10) -> dict:
    try:
        items = await client.search(query, limit=limit)
        return ok("found items", items=items)
    except Exception as e:
        return err(str(e))

if __name__ == "__main__":
    app.run()
```

## Background Only (scheduled context submissions)

```python
from truffile.app_runtime import BackgroundWorkerApp

class MyApp(BackgroundWorkerApp[MyWorker, MyResult]):
    def __init__(self):
        super().__init__("my-app", logger_name="my-app.background")

    def build_worker(self):
        return MyWorker()

    def verify_worker(self, worker):
        return worker.verify()

    def run_cycle(self, worker):
        return worker.run_cycle()

    def handle_cycle_result(self, ctx, result):
        if result.content:
            self.submit_text(ctx, content=result.content)

app = MyApp()

if __name__ == "__main__":
    app.main()
```

## Hybrid (both FG tools + BG monitoring)

Same as above but the truffile.yaml defines both foreground and background processes. They run in separate containers from the same codebase. They CANNOT communicate directly — use app variables to share state.

## Proxy MCP (wrapping an existing MCP server)

For services that already have an MCP server. Three sub-patterns:
- HTTP proxy: forward MCP requests to remote endpoint with auth headers
- Managed subprocess: launch a binary MCP server and talk via stdin/stdout
- Remote JSON-RPC client: send HTTP requests to remote MCP endpoint, parse SSE responses

## Client Architecture

Always make your API client injectable for testing:

```python
class MyClient:
    def __init__(self, auth: ApiKeyProvider, http: HttpTransport):
        self._auth = auth
        self._http = http

    async def search(self, query: str) -> list:
        headers = self._auth.get_auth_headers("GET", "/search")
        resp = await self._http.request("GET", f"{BASE_URL}/search", params={"q": query}, headers=headers)
        return resp.json()["results"]
```

This lets tests inject FakeApiKeyProvider and FakeHttpTransport.
