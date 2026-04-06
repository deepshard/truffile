from __future__ import annotations

import asyncio
import json
import socket
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent


async def call_tool(
    mcp: FastMCP,
    name: str,
    arguments: dict[str, Any] | None = None,
) -> CallToolResult:
    raw = await mcp._tool_manager.call_tool(
        name,
        arguments or {},
        context=None,
        convert_result=True,
    )
    if isinstance(raw, CallToolResult):
        return raw
    if (
        isinstance(raw, tuple)
        and len(raw) == 2
        and isinstance(raw[0], list)
        and isinstance(raw[1], dict)
    ):
        return CallToolResult(content=raw[0], structuredContent=raw[1], isError=False)
    if isinstance(raw, list):
        return CallToolResult(content=raw, isError=False)
    if isinstance(raw, dict):
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(raw, indent=2, ensure_ascii=False))],
            structuredContent=raw,
            isError=False,
        )
    return CallToolResult(content=raw, isError=False)


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class McpTestServer:
    def __init__(self, mcp: FastMCP) -> None:
        self._mcp = mcp
        self._port = 0
        self._task: asyncio.Task[None] | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    @property
    def mcp_url(self) -> str:
        return f"{self.url}/mcp"

    async def __aenter__(self) -> McpTestServer:
        import uvicorn

        self._port = _pick_free_port()
        app = self._mcp.streamable_http_app()
        config = uvicorn.Config(app, host="127.0.0.1", port=self._port, log_level="warning")
        server = uvicorn.Server(config)
        self._task = asyncio.create_task(server.serve())

        for _ in range(50):
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", self._port)
                writer.close()
                await writer.wait_closed()
                break
            except OSError:
                await asyncio.sleep(0.1)
        else:
            raise RuntimeError(f"McpTestServer failed to start on port {self._port}")
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    @asynccontextmanager
    async def client(self) -> AsyncGenerator[ClientSession, None]:
        async with streamable_http_client(self.mcp_url) as (
            read_stream,
            write_stream,
            _get_session_id,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session
