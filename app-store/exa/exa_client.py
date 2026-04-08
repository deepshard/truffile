from __future__ import annotations

import json
from typing import Any

import httpx

from truffile.app_runtime.protocols import HttpResponse, HttpTransport
from truffile.app_runtime.jsonrpc import parse_jsonrpc_payload as _parse_jsonrpc_payload, HttpxResponseAdapter

from exa_common import build_remote_url, mask_key, parse_tools_csv, read_api_key, sanitize_tool_result, selected_tool_names
from exa_verify import verify_exa_api_key


class ExaRpcError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error: dict[str, Any] | None = None,
        raw: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error or {}
        self.raw = raw or ""


class HttpxTransport:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> HttpResponse:
        response = await self._client.request(
            method,
            url,
            params=params,
            json=json,
            headers=headers,
            content=content,
        )
        return HttpxResponseAdapter(response)

    async def close(self) -> None:
        await self._client.aclose()


class ExaRemoteClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        tools: str | None = None,
        transport: HttpTransport | None = None,
    ) -> None:
        self._api_key = api_key or read_api_key()
        self._requested_tools = parse_tools_csv(tools) if tools is not None else selected_tool_names()
        self._remote_url = build_remote_url(api_key=self._api_key, base_url=base_url, tools=tools)
        self._transport = transport or HttpxTransport()
        self._session_id: str | None = None
        self._initialized = False

    @property
    def masked_api_key(self) -> str:
        return mask_key(self._api_key)

    async def close(self) -> None:
        await self._transport.close()

    async def verify(self) -> tuple[bool, str]:
        await self._initialize(force_refresh=True)
        tools = await self.list_tools()
        names = {
            str(tool.get("name"))
            for tool in tools
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        }
        if not names:
            return False, "Exa verification failed: no tools returned"

        expected = set(self._requested_tools)
        overlap = names & expected if expected else names
        if expected and not overlap:
            return (
                False,
                "Exa verification failed: key valid but expected tools missing "
                f"(expected={sorted(expected)}, got={sorted(names)})",
            )
        api_ok, api_message = await verify_exa_api_key(self._api_key)
        if not api_ok:
            return False, api_message
        return (
            True,
            f"Exa API key verified. key={self.masked_api_key} tools={len(names)} matched={len(overlap)}; {api_message}",
        )

    async def list_tools(self) -> list[dict[str, Any]]:
        payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        result = await self._request(payload)
        tools = ((result or {}).get("result") or {}).get("tools") or []
        return tools if isinstance(tools, list) else []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        }
        result = await self._request(payload)
        if "error" in result:
            error = result.get("error")
            raise ExaRpcError(
                f"Exa tool call failed for {name}: {error}",
                error=error if isinstance(error, dict) else {"message": str(error)},
            )
        return sanitize_tool_result(result.get("result"))

    async def _initialize(self, *, force_refresh: bool = False) -> str:
        if self._initialized and not force_refresh:
            return self._session_id

        if force_refresh:
            self._session_id = None
            self._initialized = False

        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "truffle-app-store-exa", "version": "1.0.0"},
            },
        }
        result = await self._request(init_payload, session_id=None)
        if "error" in result:
            error = result.get("error")
            raise ExaRpcError(
                f"Exa initialize failed: {error}",
                error=error if isinstance(error, dict) else {"message": str(error)},
            )
        self._initialized = True
        return self._session_id

    async def _request(
        self,
        payload: dict[str, Any],
        *,
        session_id: str | None = "__AUTO__",
        retry_on_auth: bool = True,
    ) -> dict[str, Any]:
        if session_id == "__AUTO__":
            if payload.get("method") != "initialize":
                await self._initialize()
                session_id = self._session_id
            else:
                session_id = None

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if session_id:
            headers["mcp-session-id"] = session_id

        response = await self._transport.request(
            "POST",
            self._remote_url,
            json=payload,
            headers=headers,
        )
        raw = response.text
        parsed = _parse_jsonrpc_payload(raw)
        lowered_headers: dict[str, str] = {}
        raw_headers = getattr(response, "headers", None)
        if raw_headers is None and hasattr(response, "_response"):
            raw_headers = getattr(response._response, "headers", None)
        if raw_headers is not None:
            lowered_headers = {str(k).lower(): str(v) for k, v in raw_headers.items()}
        session_header = lowered_headers.get("mcp-session-id")
        if session_header:
            self._session_id = session_header

        if response.status_code in {401, 403}:
            if retry_on_auth and payload.get("method") != "initialize":
                self._session_id = None
                self._initialized = False
                return await self._request(payload, session_id="__AUTO__", retry_on_auth=False)
            raise ExaRpcError(
                "Exa request unauthorized",
                status_code=response.status_code,
                error=(parsed or {}).get("error") if isinstance(parsed, dict) else None,
                raw=raw,
            )

        if response.status_code >= 400:
            raise ExaRpcError(
                f"Exa request failed with HTTP {response.status_code}",
                status_code=response.status_code,
                error=(parsed or {}).get("error") if isinstance(parsed, dict) else None,
                raw=raw,
            )

        if isinstance(parsed, dict):
            return parsed
        raise ExaRpcError("Exa request failed: response was not valid JSON-RPC", raw=raw)
