from __future__ import annotations

import json
import logging
import re
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from .errors import AppAuthError, AppRuntimeFailure
from .jsonrpc import parse_jsonrpc_payload
from .oauth import OAuth


LOGGER = logging.getLogger("app_runtime.remote_mcp")

SAFE_TOOL_NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")
READ_PREFIXES = ("get_", "list_", "search_", "read_", "fetch_", "find_", "query_", "check_")
WRITE_WORDS = ("create", "add", "update", "edit", "set", "assign", "move", "comment", "link", "save", "send")
DESTRUCTIVE_WORDS = ("delete", "remove", "cancel", "archive", "destroy", "revoke")

__all__ = [
    "RemoteMcpClient",
    "RemoteMcpOAuth",
    "RemoteMcpProxyServer",
    "RemoteMcpTool",
    "RemoteMcpToolOverride",
    "extract_resources_from_mcp_result",
    "infer_tool_annotations",
    "normalize_input_schema",
    "one_shot_payload_is_complete",
    "safe_tool_name",
    "text_from_mcp_result",
    "read_upstream_response",
    "wrap_tool_result",
]


def _first_present(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key, "") or "").strip()
        if value:
            return value
    return ""


def safe_tool_name(name: str, used: set[str] | None = None, *, fallback: str = "remote_tool") -> str:
    safe = SAFE_TOOL_NAME_RE.sub("_", str(name or "").strip()).strip("_").lower()
    if not safe:
        safe = fallback
    if safe[0].isdigit():
        safe = f"{fallback}_{safe}"
    if used is None:
        return safe
    if safe not in used:
        used.add(safe)
        return safe
    base = safe
    index = 2
    while f"{base}_{index}" in used:
        index += 1
    safe = f"{base}_{index}"
    used.add(safe)
    return safe


def infer_tool_annotations(name: str) -> dict[str, bool]:
    lowered = safe_tool_name(name).lower()
    if any(word in lowered for word in DESTRUCTIVE_WORDS):
        return {"readOnlyHint": False, "destructiveHint": True}
    if lowered.startswith(READ_PREFIXES) or lowered in {"whoami", "viewer", "me"}:
        return {"readOnlyHint": True, "destructiveHint": False}
    if any(word in lowered for word in WRITE_WORDS):
        return {"readOnlyHint": False, "destructiveHint": False}
    return {"readOnlyHint": False, "destructiveHint": False}


def normalize_input_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        schema = {}
    normalized = dict(schema)
    if normalized.get("type") != "object":
        normalized["type"] = "object"
    properties = normalized.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    normalized["properties"] = properties
    required = normalized.get("required")
    if isinstance(required, list):
        normalized["required"] = [str(key) for key in required if str(key) in properties]
        if not normalized["required"]:
            normalized.pop("required", None)
    else:
        normalized.pop("required", None)
    normalized.setdefault("additionalProperties", False)
    return normalized


def _json_payload_is_complete(payload: bytes) -> bool:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return False
    decoder = json.JSONDecoder()
    try:
        _, idx = decoder.raw_decode(text.lstrip())
    except json.JSONDecodeError:
        return False
    leading_ws = len(text) - len(text.lstrip())
    return not text[leading_ws + idx :].strip()


def _sse_payload_has_complete_event(payload: bytes) -> bool:
    normalized = payload.replace(b"\r\n", b"\n")
    return b"\n\n" in normalized and parse_jsonrpc_payload(payload.decode("utf-8", errors="replace")) is not None


def one_shot_payload_is_complete(payload: bytes, content_type: str) -> bool:
    media_type = content_type.lower().split(";", 1)[0].strip()
    if media_type == "application/json":
        return _json_payload_is_complete(payload)
    if media_type == "text/event-stream":
        return _sse_payload_has_complete_event(payload)
    return False


def read_upstream_response(resp: Any, *, method: str) -> bytes:
    content_type = str(resp.headers.get("Content-Type", "") or "")
    chunks: list[bytes] = []
    while True:
        chunk = resp.read(64 * 1024)
        if not chunk:
            break
        chunks.append(chunk)
        payload = b"".join(chunks)
        if method == "POST" and one_shot_payload_is_complete(payload, content_type):
            break
    return b"".join(chunks)


def text_from_mcp_result(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result or "")
    content = result.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text = str(item.get("text", "") or "").strip()
                if text:
                    parts.append(text)
            elif item.get("type") in {"resource", "resource_link"}:
                resource = item.get("resource") if isinstance(item.get("resource"), dict) else {}
                uri = str(item.get("uri") or resource.get("uri") or "").strip()
                if uri:
                    parts.append(f"[resource] {uri}")
        if parts:
            return "\n".join(parts)
    structured = result.get("structuredContent")
    if structured is not None:
        try:
            return json.dumps(structured, ensure_ascii=False, indent=2)
        except Exception:
            return str(structured)
    return ""


def extract_resources_from_mcp_result(result: Any) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    if not isinstance(result, dict):
        return resources
    content = result.get("content")
    if not isinstance(content, list):
        return resources
    for item in content:
        if not isinstance(item, dict) or item.get("type") not in {"resource", "resource_link"}:
            continue
        resource = item.get("resource") if isinstance(item.get("resource"), dict) else item
        uri = str(resource.get("uri", "") or "").strip()
        if not uri:
            continue
        resources.append(
            {
                "uri": uri,
                "name": str(resource.get("name", "") or item.get("name", "") or ""),
                "title": str(resource.get("title", "") or item.get("title", "") or ""),
                "mime_type": str(
                    resource.get("mimeType", "")
                    or resource.get("mime_type", "")
                    or item.get("mimeType", "")
                    or item.get("mime_type", "")
                    or ""
                ),
                "description": str(resource.get("description", "") or item.get("description", "") or ""),
            }
        )
    return resources


def wrap_tool_result(tool_name: str, arguments: dict[str, Any], result: Any) -> dict[str, Any]:
    status = "error" if isinstance(result, dict) and result.get("isError") else "success"
    structured = result.get("structuredContent") if isinstance(result, dict) else None
    text = text_from_mcp_result(result)
    wrapped: dict[str, Any] = {
        "status": status,
        "tool": tool_name,
        "query": dict(arguments or {}),
        "text": text,
        "resources": extract_resources_from_mcp_result(result),
        "provider_result": result,
    }
    if isinstance(structured, dict):
        for key in ("nextCursor", "next_cursor", "cursor", "hasMore", "has_more"):
            if key in structured:
                wrapped.setdefault("pagination", {})[key] = structured[key]
        for key, value in structured.items():
            if key not in wrapped and key not in {"content", "isError"}:
                wrapped[key] = value
    if status == "error":
        wrapped["message"] = text or "Remote MCP tool returned an error."
    else:
        wrapped["message"] = text or "Remote MCP tool completed."
    return wrapped


@dataclass(frozen=True, slots=True)
class RemoteMcpToolOverride:
    remote_name: str
    public_name: str | None = None
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] | None = None
    hidden: bool = False


@dataclass(frozen=True, slots=True)
class RemoteMcpTool:
    remote_name: str
    public_name: str
    description: str
    input_schema: dict[str, Any]
    annotations: dict[str, Any]
    provider_tool: dict[str, Any] = field(default_factory=dict)


class RemoteMcpOAuth(OAuth):
    """OAuth helper for protected remote MCP servers.

    The installed OAuth payload in app global vars is the source of truth. The
    token file remains a compatibility cache for local smoke tests and old app
    code.
    """

    def __init__(
        self,
        token_file: str | Path,
        *,
        app_var_key: str = "oauth_state",
        env_access_token: str | None = None,
        default_token_endpoint: str = "",
        default_resource: str = "",
        read_only: bool = False,
    ) -> None:
        super().__init__(Path(token_file), read_only=read_only)
        self.APP_VAR_KEY = app_var_key
        self.env_access_token = env_access_token or ""
        self.default_token_endpoint = default_token_endpoint
        self.default_resource = default_resource

    def get_access_token(self) -> str:
        if self.env_access_token:
            return self.env_access_token
        return super().get_access_token()

    def refresh_access_token(self) -> str:
        if self.env_access_token:
            raise AppAuthError("OAuth access token came from an environment override and cannot be refreshed by the app")
        payload = self.get_oauth_payload()
        if not isinstance(payload, dict):
            raise AppAuthError("OAuth payload is missing; reinstall or reconfigure the app")
        refresh_token = _first_present(payload, "refresh_token", "refreshToken")
        if not refresh_token:
            raise AppAuthError("OAuth payload is missing a refresh token; reinstall or reconfigure the app")
        client_id = _first_present(payload, "client_id", "clientId", "oauth_client_id")
        if not client_id:
            raise AppAuthError("OAuth payload is missing client_id; reinstall the app with the updated OAuth step")
        client_secret = _first_present(payload, "client_secret", "clientSecret", "oauth_client_secret")
        token_endpoint = _first_present(payload, "token_endpoint", "tokenEndpoint") or self.default_token_endpoint
        if not token_endpoint:
            raise AppAuthError("OAuth payload is missing token_endpoint; reinstall or reconfigure the app")
        resource = _first_present(payload, "resource", "oauth_resource", "audience") or self.default_resource

        form = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }
        if client_secret:
            form["client_secret"] = client_secret
        if resource:
            form["resource"] = resource
        req = urlrequest.Request(
            token_endpoint,
            data=urlparse.urlencode(form).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=30) as resp:
                body_text = resp.read().decode("utf-8", errors="replace")
        except urlerror.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise AppAuthError(f"OAuth token refresh failed ({exc.code}): {body_text[:300]}") from exc
        except Exception as exc:
            raise AppAuthError(f"OAuth token refresh failed: {exc}") from exc
        try:
            refreshed = json.loads(body_text)
        except json.JSONDecodeError as exc:
            raise AppAuthError(f"OAuth token refresh returned invalid JSON: {exc}") from exc
        if not isinstance(refreshed, dict):
            raise AppAuthError("OAuth token refresh response is not an object")
        access_token = _first_present(refreshed, "access_token")
        if not access_token:
            raise AppAuthError("OAuth token refresh response missing access_token")

        merged = dict(payload)
        merged.update(refreshed)
        merged.setdefault("refresh_token", refresh_token)
        merged.setdefault("client_id", client_id)
        if client_secret:
            merged.setdefault("client_secret", client_secret)
        merged.setdefault("token_endpoint", token_endpoint)
        if resource:
            merged.setdefault("resource", resource)
        self.save_oauth_payload(merged)
        return access_token

    def get_auth_headers(self) -> dict[str, str]:
        token = self.get_access_token()
        if not token:
            raise AppAuthError("OAuth access token is missing; reinstall or reconfigure the app")
        return {"Authorization": f"Bearer {token}"}


PostJsonRpc = Callable[
    [str, dict[str, Any]],
    tuple[int, dict[str, str], dict[str, Any] | None, str],
]


class RemoteMcpClient:
    def __init__(
        self,
        *,
        remote_url: str,
        auth: RemoteMcpOAuth | None = None,
        default_headers: dict[str, str] | None = None,
        tool_overrides: list[RemoteMcpToolOverride] | None = None,
        app_name: str = "remote_mcp",
        protocol_version: str = "2024-11-05",
        post_jsonrpc: PostJsonRpc | None = None,
    ) -> None:
        self.remote_url = remote_url
        self.auth = auth
        self.default_headers = dict(default_headers or {})
        self.app_name = app_name
        self.protocol_version = protocol_version
        self._post_jsonrpc = post_jsonrpc or self._post_jsonrpc
        self._session_id: str | None = None
        self._initialized = False
        self._tool_name_map: dict[str, str] = {}
        self._overrides = {override.remote_name: override for override in tool_overrides or []}

    def close(self) -> None:
        return None

    def verify(self) -> tuple[bool, str]:
        try:
            self._ensure_initialized()
            tools = self.list_tools()
        except AppAuthError as exc:
            return False, f"{self.app_name} verification failed: {exc}"
        except Exception as exc:
            return False, f"{self.app_name} verification failed: {exc}"
        names = ",".join(sorted(tool.public_name for tool in tools))
        return True, f"{self.app_name} MCP verified. tools={names}"

    def list_tools(self) -> list[RemoteMcpTool]:
        self._ensure_initialized()
        status, _, parsed, raw = self.send_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        if status in {401, 403} and self._refresh_auth():
            self._ensure_initialized()
            status, _, parsed, raw = self.send_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        if status in {401, 403}:
            raise AppAuthError(f"{self.app_name} tools/list unauthorized")
        if status >= 400:
            raise AppRuntimeFailure(f"{self.app_name} tools/list failed with HTTP {status}: {raw[:300]}")
        if parsed and parsed.get("error"):
            raise AppRuntimeFailure(f"{self.app_name} tools/list returned error: {parsed['error']}")
        tools = ((parsed or {}).get("result") or {}).get("tools") or []
        if not isinstance(tools, list):
            raise AppRuntimeFailure(f"{self.app_name} tools/list returned an invalid tools payload")
        normalized = self.normalize_tools(tools)
        self._tool_name_map = {tool.public_name: tool.remote_name for tool in normalized}
        return normalized

    def list_mcp_tools(self) -> list[dict[str, Any]]:
        return [self.tool_to_mcp_dict(tool) for tool in self.list_tools()]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        if not self._tool_name_map:
            self.list_tools()
        remote_name = self._tool_name_map.get(name, name)
        result = self._call_tool_once(name, remote_name, arguments)
        return wrap_tool_result(name, arguments, result)

    def list_resources(self) -> Any:
        self._ensure_initialized()
        status, _, parsed, raw = self.send_jsonrpc({"jsonrpc": "2.0", "id": 4, "method": "resources/list", "params": {}})
        if status in {401, 403} and self._refresh_auth():
            self._ensure_initialized()
            status, _, parsed, raw = self.send_jsonrpc({"jsonrpc": "2.0", "id": 4, "method": "resources/list", "params": {}})
        if status in {401, 403}:
            raise AppAuthError(f"{self.app_name} resources/list unauthorized")
        if status >= 400:
            raise AppRuntimeFailure(f"{self.app_name} resources/list failed with HTTP {status}: {raw[:300]}")
        if parsed and parsed.get("error"):
            raise AppRuntimeFailure(f"{self.app_name} resources/list returned error: {parsed['error']}")
        return (parsed or {}).get("result")

    def read_resource(self, uri: str) -> Any:
        self._ensure_initialized()
        status, _, parsed, raw = self.send_jsonrpc(
            {"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": uri}}
        )
        if status in {401, 403} and self._refresh_auth():
            self._ensure_initialized()
            status, _, parsed, raw = self.send_jsonrpc(
                {"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": uri}}
            )
        if status in {401, 403}:
            raise AppAuthError(f"{self.app_name} resources/read unauthorized")
        if status >= 400:
            raise AppRuntimeFailure(f"{self.app_name} resources/read failed with HTTP {status}: {raw[:300]}")
        if parsed and parsed.get("error"):
            raise AppRuntimeFailure(f"{self.app_name} resources/read returned error: {parsed['error']}")
        return (parsed or {}).get("result")

    def normalize_tools(self, tools: list[Any]) -> list[RemoteMcpTool]:
        used: set[str] = set()
        out: list[RemoteMcpTool] = []
        for item in tools:
            if not isinstance(item, dict):
                continue
            remote_name = str(item.get("name", "") or "").strip()
            if not remote_name:
                continue
            override = self._overrides.get(remote_name)
            if override and override.hidden:
                continue
            if override and override.public_name:
                public_name = safe_tool_name(override.public_name, used, fallback=safe_tool_name(self.app_name))
            else:
                public_name = safe_tool_name(remote_name, used, fallback=safe_tool_name(self.app_name))
            description = (
                override.description
                if override and override.description is not None
                else str(item.get("description", "") or f"Call remote MCP tool {remote_name}.")
            )
            input_schema = normalize_input_schema(
                override.input_schema
                if override and override.input_schema is not None
                else item.get("inputSchema") or item.get("input_schema")
            )
            annotations = dict(infer_tool_annotations(public_name))
            provider_annotations = item.get("annotations")
            if isinstance(provider_annotations, dict):
                annotations.update(provider_annotations)
            if override and override.annotations:
                annotations.update(override.annotations)
            out.append(
                RemoteMcpTool(
                    remote_name=remote_name,
                    public_name=public_name,
                    description=description,
                    input_schema=input_schema,
                    annotations=annotations,
                    provider_tool=dict(item),
                )
            )
        return out

    @staticmethod
    def tool_to_mcp_dict(tool: RemoteMcpTool) -> dict[str, Any]:
        return {
            "name": tool.public_name,
            "description": tool.description,
            "inputSchema": tool.input_schema,
            "annotations": tool.annotations,
        }

    def send_jsonrpc(self, payload: dict[str, Any]) -> tuple[int, dict[str, str], dict[str, Any] | None, str]:
        status, headers, parsed, raw = self._post_jsonrpc(self.remote_url, payload)
        session_id = headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        return status, headers, parsed, raw

    def _call_tool_once(self, public_name: str, remote_name: str, arguments: dict[str, Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": remote_name, "arguments": dict(arguments or {})},
        }
        status, _, parsed, raw = self.send_jsonrpc(payload)
        if status in {401, 403} and self._refresh_auth():
            self._ensure_initialized()
            status, _, parsed, raw = self.send_jsonrpc(payload)
        if status in {401, 403}:
            raise AppAuthError(f"{self.app_name} tool '{public_name}' unauthorized")
        if status >= 400:
            raise AppRuntimeFailure(f"{self.app_name} tool '{public_name}' failed with HTTP {status}: {raw[:300]}")
        if parsed and parsed.get("error"):
            message = parsed["error"]
            message_text = message.get("message") if isinstance(message, dict) else str(message)
            if "unauthorized" in str(message_text).lower() and self._refresh_auth():
                self._ensure_initialized()
                status, _, parsed, raw = self.send_jsonrpc(payload)
                if status < 400 and parsed and not parsed.get("error"):
                    return parsed.get("result")
            if "unauthorized" in str(message_text).lower():
                raise AppAuthError(str(message_text))
            raise AppRuntimeFailure(f"{self.app_name} tool '{public_name}' returned error: {message_text}")
        if not parsed or "result" not in parsed:
            raise AppRuntimeFailure(f"{self.app_name} tool '{public_name}' returned no result")
        return parsed["result"]

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        status, _, parsed, raw = self.send_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": f"truffle-{self.app_name}", "version": "1.0.0"},
                },
            }
        )
        if status in {401, 403} and self._refresh_auth():
            status, _, parsed, raw = self.send_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": self.protocol_version,
                        "capabilities": {},
                        "clientInfo": {"name": f"truffle-{self.app_name}", "version": "1.0.0"},
                    },
                }
            )
        if status in {401, 403}:
            raise AppAuthError(f"{self.app_name} initialize unauthorized")
        if status >= 400:
            raise AppRuntimeFailure(f"{self.app_name} initialize failed with HTTP {status}: {raw[:300]}")
        if parsed and parsed.get("error"):
            raise AppRuntimeFailure(f"{self.app_name} initialize returned error: {parsed['error']}")
        self._initialized = True
        with suppress(Exception):
            self.send_jsonrpc({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def _refresh_auth(self) -> bool:
        if self.auth is None:
            return False
        try:
            self.auth.refresh_access_token()
        except Exception:
            LOGGER.debug("failed to refresh remote MCP auth for %s", self.app_name, exc_info=True)
            return False
        self._initialized = False
        self._session_id = None
        return True

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        headers.update(self.default_headers)
        if self.auth is not None:
            headers.update(self.auth.get_auth_headers())
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        return headers

    def _post_jsonrpc(self, remote_url: str, payload: dict[str, Any]) -> tuple[int, dict[str, str], dict[str, Any] | None, str]:
        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(remote_url, data=body, headers=self._headers(), method="POST")
        try:
            with urlrequest.urlopen(req, timeout=30) as resp:
                raw = read_upstream_response(resp, method="POST").decode("utf-8", errors="replace")
                headers = {key.lower(): value for key, value in resp.headers.items()}
                return resp.status, headers, parse_jsonrpc_payload(raw), raw
        except urlerror.HTTPError as exc:
            raw = read_upstream_response(exc, method="POST").decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in exc.headers.items()} if exc.headers else {}
            return exc.code, headers, parse_jsonrpc_payload(raw), raw


class RemoteMcpProxyServer:
    def __init__(self, *, client: RemoteMcpClient, host: str = "0.0.0.0", port: int = 8000) -> None:
        self.client = client
        self.host = host
        self.port = int(port)
        self._httpd: ThreadingHTTPServer | None = None

    def serve_forever(self) -> None:
        handler = self._make_handler()
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._httpd.daemon_threads = True
        self._httpd.client = self.client  # type: ignore[attr-defined]
        self._httpd.serve_forever()

    def shutdown(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()

    def start_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, daemon=True)
        thread.start()
        return thread

    @staticmethod
    def _make_handler() -> type[BaseHTTPRequestHandler]:
        class RemoteMcpProxyHandler(BaseHTTPRequestHandler):
            server_version = "TruffleRemoteMcpProxy/1.0"

            def log_message(self, fmt: str, *args: Any) -> None:
                LOGGER.debug("remote MCP proxy: " + fmt, *args)

            def do_GET(self) -> None:
                if not self._is_mcp_path():
                    self._send_json(404, {"status": "error", "message": "Not found"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                try:
                    while True:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        time.sleep(15)
                except OSError:
                    return

            def do_DELETE(self) -> None:
                if not self._is_mcp_path():
                    self._send_json(404, {"status": "error", "message": "Not found"})
                    return
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self) -> None:
                request_id: Any = None
                try:
                    if not self._is_mcp_path():
                        self._send_json(404, {"status": "error", "message": "Not found"})
                        return
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    raw_body = self.rfile.read(length) if length > 0 else b""
                    request_obj = parse_jsonrpc_payload(raw_body.decode("utf-8", errors="replace")) or {}
                    if not isinstance(request_obj, dict):
                        self._send_jsonrpc_error(None, -32700, "Invalid JSON-RPC payload")
                        return
                    method = str(request_obj.get("method", "") or "")
                    request_id = request_obj.get("id")
                    client: RemoteMcpClient = self.server.client  # type: ignore[attr-defined]
                    if method == "initialize":
                        protocol_version = str(getattr(client, "protocol_version", "2024-11-05") or "2024-11-05")
                        self._send_jsonrpc_result(
                            request_id,
                            {
                                "protocolVersion": protocol_version,
                                "capabilities": {"tools": {}, "resources": {}},
                                "serverInfo": {"name": "truffle-remote-mcp-proxy", "version": "1.0.0"},
                            },
                        )
                        return
                    if method == "notifications/initialized":
                        self.send_response(202)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    if method == "tools/list":
                        tools = [client.tool_to_mcp_dict(tool) for tool in client.list_tools()]
                        self._send_jsonrpc_result(request_id, {"tools": tools})
                        return
                    if method == "tools/call":
                        params = request_obj.get("params") if isinstance(request_obj.get("params"), dict) else {}
                        name = str(params.get("name", "") or "")
                        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
                        wrapped = client.call_tool(name, arguments)
                        if (
                            isinstance(wrapped, dict)
                            and "content" in wrapped
                            and ("structuredContent" in wrapped or "isError" in wrapped)
                            and "status" not in wrapped
                        ):
                            self._send_jsonrpc_result(request_id, wrapped)
                            return
                        self._send_jsonrpc_result(
                            request_id,
                            {
                                "content": [{"type": "text", "text": wrapped.get("message", "")}],
                                "structuredContent": wrapped,
                                "isError": wrapped.get("status") == "error",
                            },
                        )
                        return
                    if method == "resources/list":
                        self._send_jsonrpc_result(request_id, client.list_resources())
                        return
                    if method == "resources/read":
                        params = request_obj.get("params") if isinstance(request_obj.get("params"), dict) else {}
                        self._send_jsonrpc_result(request_id, client.read_resource(str(params.get("uri", "") or "")))
                        return
                    status, _, parsed, raw = client.send_jsonrpc(request_obj)
                    if parsed is not None:
                        self._send_json(status, parsed)
                    else:
                        self._send_text(status, raw)
                except Exception as exc:
                    LOGGER.exception("remote MCP proxy request failed")
                    self._send_jsonrpc_error(request_id, -32603, str(exc))

            def _send_jsonrpc_result(self, request_id: Any, result: Any) -> None:
                self._send_json(200, {"jsonrpc": "2.0", "id": request_id, "result": result})

            def _send_jsonrpc_error(self, request_id: Any, code: int, message: str) -> None:
                self._send_json(200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})

            def _send_json(self, status: int, payload: Any) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_text(self, status: int, text: str) -> None:
                body = text.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _is_mcp_path(self) -> bool:
                return urlparse.urlsplit(self.path).path.rstrip("/") == "/mcp"

        return RemoteMcpProxyHandler
