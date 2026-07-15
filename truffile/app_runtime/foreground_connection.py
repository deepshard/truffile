from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .app_client import AppRuntimeClient, ForegroundMcpInfo

logger = logging.getLogger(__name__)

DEFAULT_LEASE_SECONDS = 300 #if the BG app doesn't specify a duration, the FG container lease lasts 5 minutes. if BG app crashes, worst case theFG container sits idle for 5 min + 15s (idle timeout) before cleanup
_REFRESH_RATIO = 0.8 # auto-refresh fires at 80% of the lease duration. so 
                     # for a 300s lease, it refreshes at 240s (1 min before expiry). this gives a
                     # buffer- if one refresh fails, there's still 60s before the lease expires
_CONNECT_RETRY_ATTEMPTS = 10 # worst case scenario 10 request 0.5s apart, 5s total which is enough even for cold start
_CONNECT_RETRY_DELAY = 0.5


class ForegroundConnection:
    """mcp client to this app's foreground container, with automatic lease refresh."""

    def __init__(
        self,
        app_runtime: AppRuntimeClient,
        *,
        lease_duration_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> None:
        self._app_runtime = app_runtime
        self._requested_lease = lease_duration_seconds
        self._info: ForegroundMcpInfo | None = None
        self._session: ClientSession | None = None
        self._refresh_task: asyncio.Task[None] | None = None
        self._streams: Any = None
        self._closed = False

    async def connect(self) -> ForegroundConnection:
        self._info = self._app_runtime.acquire_foreground_mcp(
            lease_duration_seconds=self._requested_lease,
        )
        self._refresh_task = asyncio.create_task(self._auto_refresh_loop())

        # fg container may still be booting — retry until mcp is ready
        last_exc: Exception | None = None
        for attempt in range(_CONNECT_RETRY_ATTEMPTS):
            try:
                self._streams = streamable_http_client(self._info.url)
                read_stream, write_stream, _ = await self._streams.__aenter__()
                self._session = ClientSession(read_stream, write_stream)
                await self._session.__aenter__()
                await self._session.initialize()
                return self
            except Exception as exc:
                last_exc = exc
                # clean up partial state before retry
                await self._close_mcp_session()
                if attempt < _CONNECT_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(_CONNECT_RETRY_DELAY)

        await self.close()
        raise ConnectionError(
            f"failed to connect to foreground MCP at {self._info.url} "
            f"after {_CONNECT_RETRY_ATTEMPTS} attempts"
        ) from last_exc

    async def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        if self._session is None:
            raise RuntimeError("not connected — call connect() first")
        result = await self._session.call_tool(tool_name, kwargs)
        return result

    async def list_tools(self) -> list[Any]:
        if self._session is None:
            raise RuntimeError("not connected — call connect() first")
        result = await self._session.list_tools()
        return list(result.tools)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self._refresh_task is not None:
            self._refresh_task.cancel()
            self._refresh_task = None

        await self._close_mcp_session()

        try:
            self._app_runtime.release_foreground_mcp()
        except Exception:
            logger.debug("failed to release foreground MCP lease (may have already expired)", exc_info=True)

    async def _close_mcp_session(self) -> None:
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
            self._session = None
        if self._streams is not None:
            try:
                await self._streams.__aexit__(None, None, None)
            except Exception:
                pass
            self._streams = None

    async def _auto_refresh_loop(self) -> None:
        while True:
            duration = self._info.lease_duration_seconds if self._info else self._requested_lease
            sleep_time = duration * _REFRESH_RATIO
            try:
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                return
            try:
                granted = self._app_runtime.refresh_foreground_mcp(
                    lease_duration_seconds=self._requested_lease,
                )
                if self._info is not None:
                    # update lease duration for next refresh cycle!
                    self._info = ForegroundMcpInfo(
                        address=self._info.address,
                        port=self._info.port,
                        path=self._info.path,
                        lease_duration_seconds=granted,
                    )
            except Exception:
                logger.warning("failed to refresh foreground mcp lease", exc_info=True)

    async def __aenter__(self) -> ForegroundConnection:
        return await self.connect()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()
