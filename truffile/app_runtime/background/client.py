from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

import grpc
from truffle.app import background_pb2
from truffle.app.background_pb2_grpc import BackgroundAppServiceStub

from ..core import RuntimeConnectionInfo, build_auth_metadata, load_runtime_connection_info

logger = logging.getLogger(__name__)

BG_SUBMIT_CONTEXT_MAX_CHARS = 80_000


class BackgroundAppClient:
    def __init__(
        self,
        channel: grpc.Channel,
        *,
        connection: RuntimeConnectionInfo | None = None,
    ) -> None:
        self._connection = connection or load_runtime_connection_info()
        self._stub = BackgroundAppServiceStub(channel)

    def on_run(self) -> background_pb2.BackgroundAppOnRunResponse:
        req = background_pb2.BackgroundAppOnRunRequest()
        return self._stub.OnRun(req, metadata=self.grpc_metadata())

    def yield_run(self) -> datetime:
        req = background_pb2.BackgroundAppYieldRequest()
        resp = self._stub.Yield(req, metadata=self.grpc_metadata())
        return resp.next_scheduled_run_time.ToDatetime(tzinfo=timezone.utc)

    def submit_context(
        self,
        *,
        content: str,
        uris: Iterable[str] = (),
        priority: int = background_pb2.BackgroundContext.PRIORITY_UNSPECIFIED,
        max_chars: int = BG_SUBMIT_CONTEXT_MAX_CHARS,
    ) -> background_pb2.BackgroundAppSubmitContextResponse:
        if len(content) > max_chars:
            original_len = len(content)
            logger.warning(
                "submit_context content is %s chars (limit: %s). Truncating.",
                f"{original_len:,}",
                f"{max_chars:,}",
            )
            content = (
                content[:max_chars]
                + f"\n\n[Content truncated: original was {original_len:,} chars, "
                f"showing first {max_chars:,}.]"
            )
        req = background_pb2.BackgroundAppSubmitContextRequest()
        req.content.content = content
        req.content.priority = priority
        req.content.uris.extend(list(uris))
        return self._stub.Submit(req, metadata=self.grpc_metadata())

    def grpc_metadata(self) -> list[tuple[str, str]]:
        return build_auth_metadata(self._connection)
