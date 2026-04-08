from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from truffile.app_runtime.errors import AppAuthError, AppRuntimeFailure

from config import (
    DEFAULT_NOTION_VERSION,
    LOCAL_MCP_HOST,
    LOCAL_MCP_PATH,
    LOCAL_STARTUP_TIMEOUT_SECONDS,
)

NOTION_API_BASE = "https://api.notion.com/v1"


def verify_notion_workspace(token: str) -> tuple[bool, str]:
    request = urlrequest.Request(
        f"{NOTION_API_BASE}/users/me",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": DEFAULT_NOTION_VERSION,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlrequest.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except urlerror.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if exc.code in {401, 403}:
            raise AppAuthError(f"Notion access token unauthorized: HTTP {exc.code} {raw[:300]}") from exc
        raise AppRuntimeFailure(f"Notion workspace check failed: HTTP {exc.code} {raw[:300]}") from exc
    except Exception as exc:
        raise AppRuntimeFailure(f"Notion workspace check failed: {exc}") from exc

    if not isinstance(payload, dict):
        raise AppRuntimeFailure("Notion users/me returned a non-object payload")

    bot_info = payload.get("bot")
    owner_info = bot_info.get("owner") if isinstance(bot_info, dict) else None
    workspace_name = ""
    workspace_label = ""

    if isinstance(bot_info, dict):
        workspace_name = str(bot_info.get("workspace_name", "") or "").strip()
    if isinstance(owner_info, dict):
        user = owner_info.get("user")
        workspace_label = str(owner_info.get("workspace_name", "") or "").strip()
        if isinstance(user, dict):
            display_name = str(user.get("name", "") or "").strip()
            if display_name:
                return True, f"workspace={workspace_name or workspace_label or 'unknown'} owner={display_name}"

    if workspace_name or workspace_label:
        return True, f"workspace={workspace_name or workspace_label}"
    return True, "workspace=connected"


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
    session_id: str | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, str], dict[str, Any] | None, str]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["mcp-session-id"] = session_id

    request = urlrequest.Request(remote_url, data=body, headers=headers, method="POST")
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            parsed = _parse_jsonrpc_payload(raw)
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return response.status, response_headers, parsed, raw
    except urlerror.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        response_headers = {key.lower(): value for key, value in exc.headers.items()} if exc.headers else {}
        parsed = _parse_jsonrpc_payload(raw)
        return exc.code, response_headers, parsed, raw


class NotionMcpClient:
    def __init__(self, *, remote_url: str, post_jsonrpc: Any = _post_jsonrpc) -> None:
        self.remote_url = remote_url
        self._post_jsonrpc = post_jsonrpc
        self._session_id: str | None = None
        self._initialized = False

    def verify(self) -> tuple[bool, str]:
        tools = self.list_tools()
        return True, f"Notion MCP verified. tools={len(tools)}"

    def list_tools(self) -> list[dict[str, Any]]:
        self._initialize()
        status, _, parsed, raw = self._send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        if status in {401, 403}:
            raise AppAuthError("Notion tools/list unauthorized")
        if status >= 400:
            raise AppRuntimeFailure(f"Notion tools/list failed with HTTP {status}: {raw[:300]}")
        if parsed and parsed.get("error"):
            raise AppRuntimeFailure(f"Notion tools/list returned error: {parsed['error']}")
        tools = ((parsed or {}).get("result") or {}).get("tools") or []
        if not isinstance(tools, list):
            raise AppRuntimeFailure("Notion tools/list returned an invalid tools payload")
        return [tool for tool in tools if isinstance(tool, dict)]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self._initialize()
        status, _, parsed, raw = self._send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        if status in {401, 403}:
            raise AppAuthError(f"Notion tool '{name}' unauthorized")
        if status >= 400:
            raise AppRuntimeFailure(f"Notion tool '{name}' failed with HTTP {status}: {raw[:300]}")
        if parsed and parsed.get("error"):
            message = parsed["error"]
            message_text = message.get("message") if isinstance(message, dict) else str(message)
            if "unauthorized" in str(message_text).lower():
                raise AppAuthError(str(message_text))
            raise AppRuntimeFailure(f"Notion tool '{name}' returned error: {message_text}")
        if not parsed or "result" not in parsed:
            raise AppRuntimeFailure(f"Notion tool '{name}' returned no result")
        return parsed["result"]

    def _initialize(self) -> None:
        if self._initialized:
            return
        status, _, parsed, raw = self._send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "truffle-app-store", "version": "1.0.0"},
                },
            }
        )
        if status in {401, 403}:
            raise AppAuthError("Notion initialize unauthorized")
        if status >= 400:
            raise AppRuntimeFailure(f"Notion initialize failed with HTTP {status}: {raw[:300]}")
        if parsed and parsed.get("error"):
            raise AppRuntimeFailure(f"Notion initialize returned error: {parsed['error']}")
        self._initialized = True

    def _send(self, payload: dict[str, Any]) -> tuple[int, dict[str, str], dict[str, Any] | None, str]:
        status, headers, parsed, raw = self._post_jsonrpc(
            self.remote_url,
            payload,
            session_id=self._session_id,
        )
        session_id = headers.get("mcp-session-id")
        if session_id:
            self._session_id = session_id
        return status, headers, parsed, raw

    def close(self) -> None:
        self._initialized = False


class ManagedNotionMcpProcessClient(NotionMcpClient):
    def __init__(
        self,
        *,
        notion_token: str,
        server_bin: str,
        process_launcher: Any = subprocess.Popen,
        startup_timeout_seconds: float = LOCAL_STARTUP_TIMEOUT_SECONDS,
    ) -> None:
        self.notion_token = notion_token
        self.server_bin = server_bin
        self._process_launcher = process_launcher
        self._startup_timeout_seconds = startup_timeout_seconds
        self._process: subprocess.Popen[bytes] | None = None
        self._stdout_log = tempfile.NamedTemporaryFile(prefix="notion-mcp-stdout-", suffix=".log", delete=False)
        self._stderr_log = tempfile.NamedTemporaryFile(prefix="notion-mcp-stderr-", suffix=".log", delete=False)
        self._local_port = self._reserve_port()
        remote_url = f"http://{LOCAL_MCP_HOST}:{self._local_port}{LOCAL_MCP_PATH}"
        super().__init__(remote_url=remote_url)
        atexit.register(self.close)

    @staticmethod
    def _reserve_port() -> int:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((LOCAL_MCP_HOST, 0))
            return int(sock.getsockname()[1])
        finally:
            sock.close()

    def _ensure_started(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return

        env = dict(os.environ)
        env["NOTION_TOKEN"] = self.notion_token
        cmd = [
            self.server_bin,
            "--transport",
            "http",
            "--port",
            str(self._local_port),
            "--disable-auth",
        ]
        self._process = self._process_launcher(
            cmd,
            env=env,
            stdout=self._stdout_log,
            stderr=self._stderr_log,
        )
        self._wait_until_ready()

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + self._startup_timeout_seconds
        last_error = ""
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                raise AppRuntimeFailure(self._startup_failure_message())
            try:
                self._initialize()
                return
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.25)
        raise AppRuntimeFailure(self._startup_failure_message(last_error=last_error))

    def _startup_failure_message(self, *, last_error: str = "") -> str:
        stderr_text = self._read_log(self._stderr_log.name)
        stdout_text = self._read_log(self._stdout_log.name)
        parts = ["Timed out starting notion-mcp-server"]
        if last_error:
            parts.append(f"last_error={last_error}")
        if stderr_text:
            parts.append(f"stderr={stderr_text[:400]}")
        if stdout_text:
            parts.append(f"stdout={stdout_text[:400]}")
        return " | ".join(parts)

    @staticmethod
    def _read_log(path: str) -> str:
        candidate = Path(path)
        if not candidate.exists():
            return ""
        try:
            return candidate.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            return ""

    def _initialize(self) -> None:
        self._ensure_started_base()
        super()._initialize()

    def _ensure_started_base(self) -> None:
        if self._process is None or self._process.poll() is not None:
            self._ensure_started()

    def list_tools(self) -> list[dict[str, Any]]:
        self._ensure_started_base()
        return super().list_tools()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self._ensure_started_base()
        return super().call_tool(name, arguments)

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                process.kill()
                process.wait(timeout=3)
        for handle in (self._stdout_log, self._stderr_log):
            try:
                handle.close()
            except Exception:
                pass

