#!/usr/bin/env python3
"""Foreground MCP proxy and harness-friendly app object for GitHub remote MCP."""

from __future__ import annotations

import argparse
import atexit
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest



from truffile.app_runtime.errors import AppAuthError, AppRuntimeFailure, ErrorReporter

from auth import GitHubAuth
from config import (
    GITHUB_MCP_BASE,
    MCP_HOST,
    MCP_PORT,
    TOKEN_EXPORT_TOOL_NAME,
    build_default_headers,
    mask_token,
)

LOGGER = logging.getLogger("github.foreground")
LOGGER.setLevel(logging.INFO)


def _local_token_export_tool() -> dict[str, Any]:
    return {
        "name": TOKEN_EXPORT_TOOL_NAME,
        "description": (
            "Return this app's installed GitHub access token for handoff into another trusted local coding app. "
            "Only call this after the user explicitly approves sharing the token."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_app": {
                    "type": "string",
                    "description": "Name of the receiving app, for example 'codex' or 'claude-code'.",
                },
                "confirm_user_consented": {
                    "type": "boolean",
                    "description": "Set true only after the user explicitly approves sharing this token.",
                },
            },
            "required": ["confirm_user_consented"],
            "additionalProperties": False,
        },
    }


def _jsonrpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _parse_jsonrpc_payload(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    candidate: dict[str, Any] | None = None
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except Exception:
            continue
        if isinstance(parsed, dict):
            candidate = parsed
    return candidate


def _post_jsonrpc(
    remote_url: str,
    payload: dict[str, Any],
    *,
    default_headers: dict[str, str],
    session_id: str | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, str], dict[str, Any] | None, str]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    headers.update(default_headers)
    if session_id:
        headers["mcp-session-id"] = session_id

    req = urlrequest.Request(remote_url, data=body, headers=headers, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = _parse_jsonrpc_payload(raw)
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp_headers, parsed, raw
    except urlerror.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        resp_headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        parsed = _parse_jsonrpc_payload(raw)
        return exc.code, resp_headers, parsed, raw


class GitHubRemoteMcpClient:
    def __init__(
        self,
        *,
        remote_url: str,
        default_headers: dict[str, str],
        post_jsonrpc: Any = _post_jsonrpc,
    ) -> None:
        self.remote_url = remote_url
        self.default_headers = dict(default_headers)
        self._post_jsonrpc = post_jsonrpc
        self._session_id: str | None = None
        self._initialized = False

    def verify(self) -> tuple[bool, str]:
        try:
            self._ensure_initialized()
        except AppAuthError:
            return False, "GitHub verification failed: unauthorized token"
        except AppRuntimeFailure as exc:
            return False, f"GitHub verification failed: {exc}"

        tools_status, _, tools_parsed, tools_raw = self._send(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        )
        if tools_status in {401, 403}:
            return False, "GitHub verification failed: tools/list unauthorized"
        if tools_status >= 400:
            return True, (
                f"GitHub access token verified from initialize; proceeding despite tools/list warning: "
                f"HTTP {tools_status} {tools_raw[:300]}"
            )
        if tools_parsed and tools_parsed.get("error"):
            return True, (
                "GitHub access token verified from initialize; proceeding despite tools/list warning: "
                f"{tools_parsed['error']}"
            )

        tools = ((tools_parsed or {}).get("result") or {}).get("tools") or []
        if not isinstance(tools, list):
            tools = []
        return True, (
            "GitHub access token verified. "
            f"token={mask_token(self.default_headers['Authorization'].removeprefix('Bearer ').strip())} "
            f"tools={len(tools)}"
        )

    def list_tools(self) -> list[dict[str, Any]]:
        self._ensure_initialized()
        status, _, parsed, raw = self._send({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})
        if status in {401, 403}:
            raise AppAuthError("GitHub tools/list unauthorized")
        if status >= 400:
            raise AppRuntimeFailure(f"GitHub tools/list failed with HTTP {status}: {raw[:300]}")
        if parsed and parsed.get("error"):
            raise AppRuntimeFailure(f"GitHub tools/list returned error: {parsed['error']}")
        tools = ((parsed or {}).get("result") or {}).get("tools") or []
        if not isinstance(tools, list):
            raise AppRuntimeFailure("GitHub tools/list returned an invalid tools payload")
        out = [tool for tool in tools if isinstance(tool, dict)]
        if not any(tool.get("name") == TOKEN_EXPORT_TOOL_NAME for tool in out):
            out.append(_local_token_export_tool())
        return out

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self._ensure_initialized()
        status, _, parsed, raw = self._send(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        if status in {401, 403}:
            raise AppAuthError(f"GitHub tool '{name}' unauthorized")
        if status >= 400:
            raise AppRuntimeFailure(f"GitHub tool '{name}' failed with HTTP {status}: {raw[:300]}")
        if parsed and parsed.get("error"):
            message = parsed["error"]
            message_text = message.get("message") if isinstance(message, dict) else str(message)
            if "unauthorized" in str(message_text).lower():
                raise AppAuthError(str(message_text))
            raise AppRuntimeFailure(f"GitHub tool '{name}' returned error: {message_text}")
        if not parsed or "result" not in parsed:
            raise AppRuntimeFailure(f"GitHub tool '{name}' returned no result")
        return parsed["result"]

    def close(self) -> None:
        return None

    def _send(self, payload: dict[str, Any]) -> tuple[int, dict[str, str], dict[str, Any] | None, str]:
        status, headers, parsed, raw = self._post_jsonrpc(
            self.remote_url,
            payload,
            default_headers=self.default_headers,
            session_id=self._session_id,
        )
        session_id = headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        return status, headers, parsed, raw

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        init_status, _, init_parsed, init_raw = self._send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "truffle-installer", "version": "1.0.0"},
                },
            }
        )
        if init_status in {401, 403}:
            raise AppAuthError("GitHub initialize unauthorized")
        if init_status >= 400:
            raise AppRuntimeFailure(f"GitHub initialize failed with HTTP {init_status}: {init_raw[:300]}")
        if init_parsed and init_parsed.get("error"):
            raise AppRuntimeFailure(f"GitHub initialize returned error: {init_parsed['error']}")
        self._initialized = True


class _StubGitHubRemoteMcpClient:
    def verify(self) -> tuple[bool, str]:
        return True, "GitHub access token verified. token=gho_...stub tools=1"

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "list_pull_requests",
                "description": "Stub GitHub MCP tool.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            _local_token_export_tool(),
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return {
            "content": [{"type": "text", "text": f"stub:{name}"}],
            "structuredContent": {"name": name, "arguments": arguments},
            "isError": False,
        }


class GitHubForegroundApp:
    def __init__(self) -> None:
        self.name = "github"
        self.logger = LOGGER
        self._error_reporter = ErrorReporter(logger=self.logger, app_name="github")
        self._client: GitHubRemoteMcpClient | None = None
        self._auth = GitHubAuth()

    def build_client(self) -> GitHubRemoteMcpClient:
        if os.getenv("APP_STORE_USE_TEST_STUBS") == "1":
            return _StubGitHubRemoteMcpClient()  # type: ignore[return-value]
        try:
            token = self._auth.load_access_token()
        except Exception as exc:
            raise AppAuthError(str(exc)) from exc
        return GitHubRemoteMcpClient(
            remote_url=GITHUB_MCP_BASE,
            default_headers=build_default_headers(token),
        )

    def get_client(self) -> GitHubRemoteMcpClient:
        if self._client is None:
            self._client = self.build_client()
        return self._client

    def set_client(self, client: GitHubRemoteMcpClient) -> None:
        self.reset_for_test()
        self._client = client

    def reset_for_test(self) -> None:
        if self._client is not None:
            close = getattr(self._client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    self.logger.exception("Failed closing GitHub MCP client")
        self._client = None

    def logger_names(self) -> list[str]:
        return [self.logger.name]

    def list_tools(self) -> list[dict[str, Any]]:
        tools = [tool for tool in self.get_client().list_tools() if isinstance(tool, dict)]
        if not any(tool.get("name") == TOKEN_EXPORT_TOOL_NAME for tool in tools):
            tools.append(_local_token_export_tool())
        return tools

    def list_prompts(self) -> list[dict[str, str]]:
        return []

    async def invoke_tool(self, name: str, **arguments: Any) -> Any:
        try:
            if name == TOKEN_EXPORT_TOOL_NAME:
                return self._handle_local_token_export(arguments)
            return self.get_client().call_tool(name, arguments)
        except Exception as exc:
            await self._error_reporter.report_foreground_exception(exc, tool_name=name)
            raise

    def _handle_local_token_export(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if arguments.get("confirm_user_consented") is not True:
            raise AppRuntimeFailure("confirm_user_consented=true is required after explicit user approval")
        target_app = str(arguments.get("target_app", "") or "").strip() or "codex"
        token = self._auth.load_access_token()
        return {
            "content": [{"type": "text", "text": token}],
            "structuredContent": {
                "access_token": token,
                "target_app": target_app,
                "source": "github_access_token",
            },
            "isError": False,
        }

    def verify(self) -> tuple[bool, str]:
        return self.build_client().verify()

    def run(self) -> None:
        try:
            client = self.build_client()
        except Exception as exc:
            LOGGER.error("Cannot start GitHub MCP proxy: %s", exc)
            raise SystemExit(1) from exc

        server = ThreadingHTTPServer((MCP_HOST, MCP_PORT), GitHubMCPProxyHandler)
        server.remote_url = client.remote_url  # type: ignore[attr-defined]
        server.default_headers = client.default_headers  # type: ignore[attr-defined]

        LOGGER.info(
            "Starting GitHub MCP proxy on %s:%d -> %s",
            MCP_HOST,
            MCP_PORT,
            client.remote_url,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            LOGGER.info("GitHub MCP proxy stopped")
        finally:
            server.server_close()


app = GitHubForegroundApp()


class GitHubMCPProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        LOGGER.info("github-proxy: " + fmt, *args)

    def do_POST(self) -> None:
        self._forward("POST")

    def do_GET(self) -> None:
        self._forward("GET")

    def do_DELETE(self) -> None:
        self._forward("DELETE")

    def _forward(self, method: str) -> None:
        parsed = urlparse.urlsplit(self.path)
        if parsed.path.rstrip("/") != "/mcp":
            self._send_json_error(404, "Not found")
            return

        remote_url = self.server.remote_url  # type: ignore[attr-defined]
        if parsed.query:
            sep = "&" if urlparse.urlsplit(remote_url).query else "?"
            remote_url = f"{remote_url}{sep}{parsed.query}"

        body: bytes | None = None
        if method in {"POST", "PUT", "PATCH"}:
            raw_len = self.headers.get("Content-Length")
            length = int(raw_len) if raw_len and raw_len.isdigit() else 0
            body = self.rfile.read(length) if length > 0 else b""

        if method == "POST" and self._maybe_handle_local_mcp_request(body or b"", remote_url):
            return

        outbound_headers: dict[str, str] = {}
        outbound_lower: set[str] = set()
        for key, value in self.headers.items():
            lk = key.lower()
            if lk in {"host", "content-length", "connection", "proxy-connection", "accept-encoding"}:
                continue
            outbound_headers[key] = value
            outbound_lower.add(lk)

        defaults: dict[str, str] = self.server.default_headers  # type: ignore[attr-defined]
        for key, value in defaults.items():
            lk = key.lower()
            if lk == "authorization":
                outbound_headers[key] = value
                outbound_lower.add(lk)
                continue
            if lk not in outbound_lower:
                outbound_headers[key] = value
                outbound_lower.add(lk)

        req = urlrequest.Request(remote_url, data=body, headers=outbound_headers, method=method)
        try:
            with urlrequest.urlopen(req, timeout=600) as resp:
                self.send_response(resp.status)
                self._copy_response_headers(resp.headers)
                self.end_headers()
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except urlerror.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            if exc.headers:
                self._copy_response_headers(exc.headers)
            self.end_headers()
            if payload:
                self.wfile.write(payload)
                self.wfile.flush()
        except Exception as exc:
            LOGGER.exception("Failed proxy request to GitHub MCP")
            self._send_json_error(502, f"Upstream proxy error: {exc}")

    def _maybe_handle_local_mcp_request(self, body: bytes, remote_url: str) -> bool:
        payload = self._parse_request_payload(body)
        if payload is None:
            return False
        method = str(payload.get("method", "") or "").strip()
        if method == "tools/list":
            return self._handle_tools_list_with_local_tool(payload, remote_url)
        if method == "tools/call":
            params = payload.get("params")
            if not isinstance(params, dict):
                return False
            if str(params.get("name", "") or "").strip() != TOKEN_EXPORT_TOOL_NAME:
                return False
            response = app._handle_local_token_export(dict(params.get("arguments") or {}))
            self._send_json_payload(_jsonrpc_result(payload.get("id"), response))
            return True
        return False

    def _parse_request_payload(self, body: bytes) -> dict[str, Any] | None:
        try:
            decoded = body.decode("utf-8", errors="strict")
            parsed = json.loads(decoded)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _handle_tools_list_with_local_tool(self, payload: dict[str, Any], remote_url: str) -> bool:
        defaults: dict[str, str] = self.server.default_headers  # type: ignore[attr-defined]
        session_id = self.headers.get("mcp-session-id")
        status, headers, parsed, raw = _post_jsonrpc(
            remote_url,
            payload,
            default_headers=defaults,
            session_id=session_id,
        )
        extra_headers: dict[str, str] = {}
        mcp_session_id = headers.get("mcp-session-id")
        if mcp_session_id:
            extra_headers["mcp-session-id"] = mcp_session_id

        if parsed and isinstance(parsed, dict):
            result_obj = parsed.get("result")
            if isinstance(result_obj, dict):
                tools = result_obj.get("tools")
                if isinstance(tools, list) and not any(
                    isinstance(tool, dict) and tool.get("name") == TOKEN_EXPORT_TOOL_NAME for tool in tools
                ):
                    tools.append(_local_token_export_tool())
            self._send_json_payload(parsed, status=status, extra_headers=extra_headers)
            return True

        self._send_raw_payload(
            raw.encode("utf-8", errors="replace"),
            status=status,
            content_type=headers.get("content-type", "application/json"),
            extra_headers=extra_headers,
        )
        return True

    def _copy_response_headers(self, headers: Any) -> None:
        for key, value in headers.items():
            lk = key.lower()
            if lk in {
                "transfer-encoding",
                "connection",
                "keep-alive",
                "proxy-authenticate",
                "proxy-authorization",
                "te",
                "trailers",
                "upgrade",
            }:
                continue
            self.send_header(key, value)

    def _send_raw_payload(
        self,
        payload: bytes,
        *,
        status: int = 200,
        content_type: str = "application/json",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if payload:
            self.wfile.write(payload)
            self.wfile.flush()

    def _send_json_payload(
        self,
        payload: dict[str, Any],
        *,
        status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_raw_payload(body, status=status, content_type="application/json", extra_headers=extra_headers)

    def _send_json_error(self, status: int, message: str) -> None:
        payload = json.dumps({"status": "error", "message": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()


def verify() -> int:
    try:
        ok, message = app.verify()
    except Exception as exc:
        _eprint(f"GitHub verification failed: {exc}")
        return 1
    if ok:
        print(message, flush=True)
        return 0
    _eprint(message)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub MCP proxy")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify GitHub access token by calling initialize + tools/list.",
    )
    args = parser.parse_args()
    if args.verify:
        return verify()
    app.run()
    return 0


def set_client(client: GitHubRemoteMcpClient) -> None:
    app.set_client(client)


def reset_for_test() -> None:
    app.reset_for_test()


atexit.register(reset_for_test)


if __name__ == "__main__":
    raise SystemExit(main())
