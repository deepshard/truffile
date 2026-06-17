from __future__ import annotations

import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib import request as urlrequest
from unittest.mock import patch

from foreground import (
    ViatorMCPProxyHandler,
    ViatorRemoteMcpClient,
    _one_shot_payload_is_complete,
    _parse_jsonrpc_payload,
    _read_upstream_response,
)


class TestViatorRemoteMcpClient(unittest.TestCase):
    def test_parse_jsonrpc_payload_accepts_plain_json(self) -> None:
        parsed = _parse_jsonrpc_payload('{"jsonrpc":"2.0","id":1,"result":{"ok":true}}')
        self.assertEqual(parsed, {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

    def test_parse_jsonrpc_payload_accepts_sse_data_lines(self) -> None:
        parsed = _parse_jsonrpc_payload('event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n')
        self.assertEqual(parsed, {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

    def test_one_shot_json_payload_detection(self) -> None:
        self.assertTrue(_one_shot_payload_is_complete(b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}', "application/json"))
        self.assertFalse(_one_shot_payload_is_complete(b'{"jsonrpc":"2.0","id":1,"result":', "application/json"))

    def test_read_upstream_response_stops_after_complete_post_json(self) -> None:
        class FakeResponse:
            headers = {"Content-Type": "application/json"}

            def __init__(self) -> None:
                self.read_calls = 0

            def read(self, _size: int) -> bytes:
                self.read_calls += 1
                if self.read_calls == 1:
                    return b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}'
                raise AssertionError("read should stop after a complete JSON-RPC response")

        response = FakeResponse()
        payload = _read_upstream_response(response, method="POST")

        self.assertEqual(payload, b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}')
        self.assertEqual(response.read_calls, 1)

    def test_list_tools_initializes_session_first(self) -> None:
        calls: list[str] = []

        def fake_post_jsonrpc(remote_url, payload, *, default_headers, session_id=None, timeout=30):
            del remote_url, default_headers, timeout
            method = str(payload.get("method", ""))
            calls.append(method)
            if method == "initialize":
                self.assertEqual(payload["params"]["protocolVersion"], "2025-06-18")
                return 200, {"mcp-session-id": "session-123"}, {"result": {"protocolVersion": "2025-06-18"}}, "{}"
            if method == "notifications/initialized":
                return 200, {}, {"result": {}}, "{}"
            if method == "tools/list":
                self.assertEqual(session_id, "session-123")
                return 200, {}, {"result": {"tools": [{"name": "search_experiences"}, {"name": "get_experience_details"}]}}, "{}"
            raise AssertionError(f"Unexpected method: {method}")

        client = ViatorRemoteMcpClient(
            remote_url="https://example.com/mcp",
            post_jsonrpc=fake_post_jsonrpc,
        )

        tools = client.list_tools()

        self.assertEqual(calls, ["initialize", "notifications/initialized", "tools/list"])
        self.assertEqual([tool.public_name for tool in tools], ["search_experiences", "get_experience_details"])

    def test_call_tool_initializes_session_first(self) -> None:
        calls: list[str] = []

        def fake_post_jsonrpc(remote_url, payload, *, default_headers, session_id=None, timeout=30):
            del remote_url, default_headers, timeout
            method = str(payload.get("method", ""))
            calls.append(method)
            if method == "initialize":
                self.assertEqual(payload["params"]["protocolVersion"], "2025-06-18")
                return 200, {"mcp-session-id": "session-456"}, {"result": {"protocolVersion": "2025-06-18"}}, "{}"
            if method == "notifications/initialized":
                return 200, {}, {"result": {}}, "{}"
            if method == "tools/list":
                self.assertEqual(session_id, "session-456")
                return 200, {}, {"result": {"tools": [{"name": "search_experiences"}]}}, "{}"
            if method == "tools/call":
                self.assertEqual(session_id, "session-456")
                self.assertEqual(payload["params"]["name"], "search_experiences")
                self.assertEqual(
                    payload["params"]["arguments"],
                    {"searchTerm": "Paris tours", "currency": "USD"},
                )
                return (
                    200,
                    {},
                    {
                        "result": {
                            "content": [{"type": "text", "text": "ok"}],
                            "structuredContent": {
                                "sessionId": "session-456",
                                "experiences": [
                                    {
                                        "title": "Paris Food Tour",
                                        "code": "PARIS1",
                                        "thumbnail": "https://example.com/paris.jpg",
                                        "rating": 4.86,
                                        "reviewCount": 123,
                                        "freeCancellation": True,
                                        "fromPrice": 59.0,
                                        "clickOffToLander": "https://www.viator.com/tours/paris/PARIS1",
                                        "duration": {"fixedDurationInMinutes": 120},
                                        "keyAttributes": {"features": ["KID_FRIENDLY"], "mainCategory": "Food Tours"},
                                    }
                                ],
                            },
                            "isError": False,
                        }
                    },
                    "{}",
                )
            raise AssertionError(f"Unexpected method: {method}")

        client = ViatorRemoteMcpClient(
            remote_url="https://example.com/mcp",
            post_jsonrpc=fake_post_jsonrpc,
        )

        result = client.call_tool(
            "search_experiences",
            {"searchTerm": "Paris tours", "currency": "USD", "include_images": True},
        )

        self.assertEqual(calls, ["initialize", "notifications/initialized", "tools/list", "tools/call"])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tool"], "search_experiences")
        self.assertEqual(result["count"], 1)
        self.assertNotIn("text", result)
        self.assertNotIn("message", result)
        self.assertNotIn("provider_result", result)
        self.assertEqual(
            result["experiences"][0],
            {
                "code": "PARIS1",
                "title": "Paris Food Tour",
                "price_from": {"amount": 59, "currency": "USD"},
                "rating": 4.9,
                "review_count": 123,
                "category": "Food Tours",
                "free_cancellation": True,
                "product_url": "https://www.viator.com/tours/paris/PARIS1",
                "duration_minutes": 120,
                "image_url": "https://example.com/paris.jpg",
            },
        )

    def test_get_experience_details_compacts_and_gates_verbose_fields(self) -> None:
        def fake_post_jsonrpc(remote_url, payload, *, default_headers, session_id=None, timeout=30):
            del remote_url, default_headers, session_id, timeout
            method = str(payload.get("method", ""))
            if method == "initialize":
                return 200, {"mcp-session-id": "session-789"}, {"result": {"protocolVersion": "2025-06-18"}}, "{}"
            if method == "notifications/initialized":
                return 200, {}, {"result": {}}, "{}"
            if method == "tools/list":
                return 200, {}, {"result": {"tools": [{"name": "get_experience_details"}]}}, "{}"
            if method == "tools/call":
                self.assertEqual(
                    payload["params"]["arguments"],
                    {"code": "PARIS1", "currency": "USD"},
                )
                description = "A" * 650
                return (
                    200,
                    {},
                    {
                        "result": {
                            "content": [{"type": "text", "text": "raw text should not be duplicated"}],
                            "structuredContent": {
                                "sessionId": "session-789",
                                "experienceDetails": {
                                    "code": "PARIS1",
                                    "title": "Paris Food Tour",
                                    "description": description,
                                    "thumbnail": "https://example.com/paris.jpg",
                                    "rating": 4.72,
                                    "reviewCount": 44,
                                    "freeCancellation": True,
                                    "clickOffToPDP": "https://www.viator.com/tours/paris/PARIS1",
                                    "meetingPoint": "Cafe de Paris",
                                    "reviews": [
                                        {"rating": 5, "title": "Great", "text": "Loved it", "userName": "Ada"},
                                        {"rating": 4, "title": "Good", "text": "Worth it", "userName": "Grace"},
                                    ],
                                },
                            },
                            "isError": False,
                        }
                    },
                    "{}",
                )
            raise AssertionError(f"Unexpected method: {method}")

        client = ViatorRemoteMcpClient(
            remote_url="https://example.com/mcp",
            post_jsonrpc=fake_post_jsonrpc,
        )

        result = client.call_tool(
            "get_experience_details",
            {
                "code": "PARIS1",
                "currency": "USD",
                "max_chars": 25,
                "include_images": True,
                "include_details": True,
                "include_reviews": True,
                "review_limit": 1,
                "include_raw": True,
            },
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tool"], "get_experience_details")
        self.assertNotIn("text", result)
        self.assertNotIn("message", result)
        self.assertEqual(result["sessionId"], "session-789")
        experience = result["experience"]
        self.assertEqual(experience["code"], "PARIS1")
        self.assertEqual(experience["description"], "A" * 25)
        self.assertTrue(experience["description_truncated"])
        self.assertEqual(experience["image_url"], "https://example.com/paris.jpg")
        self.assertEqual(experience["details"]["meeting_point"], "Cafe de Paris")
        self.assertEqual(len(experience["reviews"]), 1)
        self.assertIn("provider_result", result)

    def test_rate_limit_retries_then_returns_compact_status(self) -> None:
        calls = 0

        def fake_post_jsonrpc(remote_url, payload, *, default_headers, session_id=None, timeout=30):
            nonlocal calls
            del remote_url, default_headers, session_id, timeout
            method = str(payload.get("method", ""))
            if method == "initialize":
                return 200, {}, {"result": {"protocolVersion": "2025-06-18"}}, "{}"
            if method == "notifications/initialized":
                return 200, {}, {"result": {}}, "{}"
            if method == "tools/list":
                return 200, {}, {"result": {"tools": [{"name": "search_experiences"}]}}, "{}"
            if method == "tools/call":
                calls += 1
                return 429, {"Retry-After": "0"}, {"error": {"message": "Too many requests"}}, "Too many requests"
            raise AssertionError(f"Unexpected method: {method}")

        client = ViatorRemoteMcpClient(
            remote_url="https://example.com/mcp",
            post_jsonrpc=fake_post_jsonrpc,
        )

        with patch("foreground.time.sleep") as sleep:
            result = client.call_tool("search_experiences", {"searchTerm": "Paris tours"})

        self.assertEqual(calls, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(
            result,
            {
                "status": "rate_limited",
                "tool": "search_experiences",
                "message": "Viator rate limit reached after 3 attempts.",
                "retry_after_seconds": 0,
                "attempts": 3,
            },
        )

    def test_verify_requires_expected_tools(self) -> None:
        def fake_post_jsonrpc(remote_url, payload, *, default_headers, session_id=None, timeout=30):
            del remote_url, default_headers, session_id, timeout
            method = str(payload.get("method", ""))
            if method == "initialize":
                return 200, {}, {"result": {"protocolVersion": "2025-06-18"}}, "{}"
            if method == "notifications/initialized":
                return 200, {}, {"result": {}}, "{}"
            if method == "tools/list":
                return 200, {}, {"result": {"tools": [{"name": "search_experiences"}]}}, "{}"
            raise AssertionError(f"Unexpected method: {method}")

        client = ViatorRemoteMcpClient(
            remote_url="https://example.com/mcp",
            post_jsonrpc=fake_post_jsonrpc,
        )

        ok, message = client.verify()

        self.assertFalse(ok)
        self.assertIn("missing tools=get_experience_details", message)

    def test_verify_reports_tool_names(self) -> None:
        def fake_post_jsonrpc(remote_url, payload, *, default_headers, session_id=None, timeout=30):
            del remote_url, default_headers, session_id, timeout
            method = str(payload.get("method", ""))
            if method == "initialize":
                return 200, {}, {"result": {"protocolVersion": "2025-06-18"}}, "{}"
            if method == "notifications/initialized":
                return 200, {}, {"result": {}}, "{}"
            if method == "tools/list":
                return 200, {}, {"result": {"tools": [{"name": "get_experience_details"}, {"name": "search_experiences"}]}}, "{}"
            raise AssertionError(f"Unexpected method: {method}")

        client = ViatorRemoteMcpClient(
            remote_url="https://example.com/mcp",
            post_jsonrpc=fake_post_jsonrpc,
        )

        ok, message = client.verify()

        self.assertTrue(ok)
        self.assertIn("get_experience_details,search_experiences", message)

    def test_403_reports_ip_whitelist_problem(self) -> None:
        def fake_post_jsonrpc(remote_url, payload, *, default_headers, session_id=None, timeout=30):
            del remote_url, payload, default_headers, session_id, timeout
            return 403, {}, {"error": {"message": "Forbidden"}}, "Forbidden"

        client = ViatorRemoteMcpClient(
            remote_url="https://example.com/mcp",
            post_jsonrpc=fake_post_jsonrpc,
        )

        ok, message = client.verify()

        self.assertFalse(ok)
        self.assertIn("client IP is not whitelisted", message)


class TestViatorMCPProxyHandler(unittest.TestCase):
    def _start_server(self) -> tuple[ThreadingHTTPServer, threading.Thread]:
        server = ThreadingHTTPServer(("127.0.0.1", 0), ViatorMCPProxyHandler)
        server.daemon_threads = True
        server.remote_url = "http://127.0.0.1:1/should-not-be-called"  # type: ignore[attr-defined]
        server.default_headers = {}  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread

    def test_get_mcp_is_served_locally_as_sse_stream(self) -> None:
        server, thread = self._start_server()
        try:
            with urlrequest.urlopen(f"http://127.0.0.1:{server.server_port}/mcp", timeout=2) as resp:
                self.assertEqual(resp.status, 200)
                self.assertEqual(resp.headers.get_content_type(), "text/event-stream")
                self.assertEqual(resp.readline(), b": keepalive\n")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_delete_mcp_is_served_locally(self) -> None:
        server, thread = self._start_server()
        try:
            request = urlrequest.Request(f"http://127.0.0.1:{server.server_port}/mcp", method="DELETE")
            with urlrequest.urlopen(request, timeout=2) as resp:
                self.assertEqual(resp.status, 204)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
