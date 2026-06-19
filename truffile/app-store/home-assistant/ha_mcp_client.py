from __future__ import annotations

from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from config import HomeAssistantConfig, load_config


class HomeAssistantMcpError(RuntimeError):
    pass


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    return value


def _drop_none(arguments: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in arguments.items() if value is not None}


class HomeAssistantMcpClient:
    def __init__(self, config: HomeAssistantConfig | None = None) -> None:
        self.config = config or load_config()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.token}",
            "Accept": "application/json, text/event-stream",
        }

    async def verify(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                response = await client.get(self.config.rest_api_url, headers=self._headers)
                response.raise_for_status()
        except Exception as exc:
            return False, f"Home Assistant REST API verification failed: {exc}"

        try:
            tools = await self.list_tools()
        except Exception as exc:
            return False, f"Home Assistant MCP verification failed at {self.config.mcp_url}: {exc}"

        return True, f"Verified Home Assistant MCP at {self.config.mcp_url} with {len(tools)} tools."

    async def verify_payload(self) -> dict[str, Any]:
        ok, message = await self.verify()
        return {
            "ok": ok,
            "message": message,
            "base_url": self.config.base_url,
            "mcp_url": self.config.mcp_url,
        }

    async def _with_session(self):
        return streamablehttp_client(
            self.config.mcp_url,
            headers=self._headers,
            timeout=30,
            sse_read_timeout=90,
        )

    async def list_tools(self) -> list[dict[str, Any]]:
        async with await self._with_session() as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_tools()
                return [_to_jsonable(tool) for tool in result.tools]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        async with await self._with_session() as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(name, _drop_none(arguments or {}))
                return _to_jsonable(result)

    async def list_resources(self) -> list[dict[str, Any]]:
        async with await self._with_session() as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_resources()
                return [_to_jsonable(resource) for resource in result.resources]

    async def read_resource(self, uri: str) -> dict[str, Any]:
        async with await self._with_session() as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.read_resource(uri)
                return _to_jsonable(result)

    async def list_prompts(self) -> list[dict[str, Any]]:
        async with await self._with_session() as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.list_prompts()
                return [_to_jsonable(prompt) for prompt in result.prompts]
