import asyncio
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import truffile
from truffle.os.task_queries_pb2 import GetTaskInfosResponse
from truffile.transport.client import GRPC_MAX_MESSAGE_BYTES, TruffleClient


class _ReadyChannel:
    async def channel_ready(self) -> None:
        return None


def test_connect_sets_grpc_message_size_limits(monkeypatch):
    captured = {}
    fake_channel = _ReadyChannel()

    def fake_insecure_channel(address, options=None):
        captured["address"] = address
        captured["options"] = options
        return fake_channel

    monkeypatch.setattr("truffile.transport.client.aio.insecure_channel", fake_insecure_channel)
    monkeypatch.setattr("truffile.transport.client.TruffleOSStub", Mock(return_value="stub"))

    client = TruffleClient("127.0.0.1:80", token="token")
    asyncio.run(client.connect())

    assert client.channel is fake_channel
    assert client.stub == "stub"
    assert captured["address"] == "127.0.0.1:80"
    assert captured["options"] == [
        ("grpc.max_receive_message_length", GRPC_MAX_MESSAGE_BYTES),
        ("grpc.max_send_message_length", GRPC_MAX_MESSAGE_BYTES),
    ]


def test_init_prepends_repo_root_for_bundled_truffle(monkeypatch):
    repo_root = str(Path(truffile.__file__).resolve().parent.parent)
    monkeypatch.setattr(sys, "path", ["/tmp/external"])

    truffile._ensure_bundled_truffle_on_path()

    assert sys.path[0] == repo_root


def test_get_task_infos_returns_requested_count_newest_first():
    response = GetTaskInfosResponse()
    for task_id, updated in [
        ("older", datetime(2026, 7, 14, 10, 0)),
        ("newer", datetime(2026, 7, 14, 12, 0)),
        ("newest", datetime(2026, 7, 14, 13, 0)),
    ]:
        entry = response.entries.add()
        entry.task_id = task_id
        entry.info.task_title = task_id
        entry.info.created.FromDatetime(updated)
        entry.info.last_updated.FromDatetime(updated)

    class _Stub:
        async def Task_GetTaskInfos(self, request, metadata):
            assert request.max_before == 2
            assert metadata == [("session", "token")]
            return response

    client = TruffleClient("127.0.0.1:80", token="token")
    client.stub = _Stub()

    tasks = asyncio.run(client.get_task_infos(max_before=2))

    assert [task["task_id"] for task in tasks] == ["newest", "newer"]
