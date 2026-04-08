from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from exa_client import ExaRemoteClient, ExaRpcError
from exa_common import build_remote_url, parse_tools_csv
from exa_verify import verify_exa_api_key

class _SequenceResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._text = text
        self.headers = headers or {}
        self.url = "https://mcp.exa.ai/mcp"

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 400

    @property
    def text(self) -> str:
        return self._text

    def json(self) -> object:
        raise NotImplementedError

    def raise_for_status(self) -> None:
        if not self.is_success:
            raise RuntimeError(f"HTTP {self.status_code}")

class _SequenceTransport:
    def __init__(self, responses: list[_SequenceResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, object] | None = None,
        json: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> _SequenceResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json": json,
                "headers": headers,
                "content": content,
            }
        )
        if not self._responses:
            raise AssertionError("unexpected request with no queued response")
        return self._responses.pop(0)

    async def close(self) -> None:
        return None

class _FakeSearchResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

class _FakeSearchClient:
    def __init__(self, response: _FakeSearchResponse | Exception) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> _FakeSearchClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> _FakeSearchResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

class TestExaUnit(unittest.IsolatedAsyncioTestCase):
    def test_parse_tools_csv_dedupes_and_preserves_order(self) -> None:
        self.assertEqual(
            parse_tools_csv("web_search_exa, people_search_exa, web_search_exa, , crawling_exa"),
            ["web_search_exa", "people_search_exa", "crawling_exa"],
        )

    def test_build_remote_url_includes_api_key_and_tools(self) -> None:
        url = build_remote_url(
            api_key="exa_test_key",
            base_url="https://mcp.exa.ai/mcp",
            tools="web_search_exa,people_search_exa",
        )
        self.assertIn("exaApiKey=exa_test_key", url)
        self.assertIn("tools=web_search_exa%2Cpeople_search_exa", url)

    async def test_verify_calls_initialize_and_tools_list(self) -> None:
        transport = _SequenceTransport(
            [
                _SequenceResponse(
                    text='{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}',
                    headers={"mcp-session-id": "exa-session-1"},
                ),
                _SequenceResponse(
                    text=(
                        '{"jsonrpc":"2.0","id":2,"result":{"tools":'
                        '[{"name":"web_search_exa"},{"name":"people_search_exa"}]}}'
                    ),
                ),
            ]
        )
        client = ExaRemoteClient(api_key="exa_test_key", transport=transport, tools="web_search_exa,people_search_exa")

        with patch("exa_client.verify_exa_api_key", return_value=(True, "direct api ok")):
            ok, message = await client.verify()

        self.assertTrue(ok)
        self.assertIn("verified", message.lower())
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(transport.calls[0]["json"]["method"], "initialize")
        self.assertEqual(transport.calls[1]["json"]["method"], "tools/list")

    async def test_verify_succeeds_when_initialize_returns_no_session_header(self) -> None:
        transport = _SequenceTransport(
            [
                _SequenceResponse(
                    text='{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}',
                ),
                _SequenceResponse(
                    text=(
                        '{"jsonrpc":"2.0","id":2,"result":{"tools":'
                        '[{"name":"web_search_exa"},{"name":"people_search_exa"}]}}'
                    ),
                ),
            ]
        )
        client = ExaRemoteClient(api_key="exa_test_key", transport=transport, tools="web_search_exa,people_search_exa")

        with patch("exa_client.verify_exa_api_key", return_value=(True, "direct api ok")):
            ok, message = await client.verify()

        self.assertTrue(ok)
        self.assertIn("verified", message.lower())
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(transport.calls[0]["json"]["method"], "initialize")
        self.assertEqual(transport.calls[1]["json"]["method"], "tools/list")
        self.assertNotIn("mcp-session-id", transport.calls[1]["headers"])

    async def test_verify_propagates_direct_api_failure(self) -> None:
        transport = _SequenceTransport(
            [
                _SequenceResponse(
                    text='{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}',
                    headers={"mcp-session-id": "exa-session-1"},
                ),
                _SequenceResponse(
                    text='{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"web_search_exa"}]}}',
                ),
            ]
        )
        client = ExaRemoteClient(api_key="exa_test_key", transport=transport, tools="web_search_exa")

        with patch("exa_client.verify_exa_api_key", return_value=(False, "Exa API key is invalid")):
            ok, message = await client.verify()

        self.assertFalse(ok)
        self.assertIn("invalid", message.lower())

    async def test_call_tool_raises_on_remote_error(self) -> None:
        transport = _SequenceTransport(
            [
                _SequenceResponse(
                    text='{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}',
                    headers={"mcp-session-id": "exa-session-1"},
                ),
                _SequenceResponse(
                    text='{"jsonrpc":"2.0","id":3,"error":{"code":-32000,"message":"bad query"}}',
                ),
            ]
        )
        client = ExaRemoteClient(
            api_key="exa_test_key",
            transport=transport,
            tools="web_search_exa",
        )

        with self.assertRaises(ExaRpcError) as ctx:
            await client.call_tool("web_search_exa", {"query": "bad query"})

        self.assertIn("bad query", str(ctx.exception))

    async def test_call_tool_retries_after_auth_failure(self) -> None:
        transport = _SequenceTransport(
            [
                _SequenceResponse(
                    text='{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}',
                    headers={"mcp-session-id": "exa-session-1"},
                ),
                _SequenceResponse(status_code=401, text='{"jsonrpc":"2.0","id":3,"error":{"message":"unauthorized"}}'),
                _SequenceResponse(
                    text='{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}',
                    headers={"mcp-session-id": "exa-session-2"},
                ),
                _SequenceResponse(
                    text='{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"ok"}]}}',
                ),
            ]
        )
        client = ExaRemoteClient(
            api_key="exa_test_key",
            transport=transport,
            tools="web_search_exa",
        )

        result = await client.call_tool("web_search_exa", {"query": "fresh"})

        self.assertEqual(result["content"][0]["text"], "ok")
        self.assertEqual(len(transport.calls), 4)

    async def test_verify_exa_api_key_succeeds_with_search_response(self) -> None:
        fake_client = _FakeSearchClient(_FakeSearchResponse(200, {"results": [{"url": "https://example.com"}]}))

        with patch("exa_verify.httpx.AsyncClient", return_value=fake_client):
            ok, message = await verify_exa_api_key("exa_test_key")

        self.assertTrue(ok)
        self.assertIn("verified", message.lower())
        self.assertEqual(fake_client.calls[0]["headers"]["x-api-key"], "exa_test_key")
        self.assertEqual(fake_client.calls[0]["json"]["query"], "hello")

    async def test_verify_exa_api_key_rejects_unauthorized(self) -> None:
        fake_client = _FakeSearchClient(_FakeSearchResponse(401, {"error": "unauthorized"}))

        with patch("exa_verify.httpx.AsyncClient", return_value=fake_client):
            ok, message = await verify_exa_api_key("exa_test_key")

        self.assertFalse(ok)
        self.assertIn("invalid", message.lower())

    async def test_verify_exa_api_key_reports_transport_error(self) -> None:
        fake_client = _FakeSearchClient(httpx.ConnectError("boom"))

        with patch("exa_verify.httpx.AsyncClient", return_value=fake_client):
            ok, message = await verify_exa_api_key("exa_test_key")

        self.assertFalse(ok)
        self.assertIn("request failed", message.lower())

if __name__ == "__main__":
    unittest.main()
