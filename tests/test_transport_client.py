import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import truffile
from truffle.os.task_actions_pb2 import TaskRenameResponse
from truffle.os.task_pb2 import Task
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


def test_get_task_uses_unary_lookup_with_nodes():
    stub = Mock()
    stub.Task_GetOneTask = AsyncMock(return_value="task")
    client = TruffleClient("127.0.0.1:80", token="token")
    client.stub = stub

    result = asyncio.run(client.get_task("task-123", with_nodes=True))

    assert result == "task"
    request = stub.Task_GetOneTask.await_args.args[0]
    assert request.task_id == "task-123"
    assert request.with_nodes is True


def test_bundled_protocol_and_app_runtime_are_importable():
    from truffle.os import truffleos_pb2  # noqa: F401
    from truffile import app_runtime  # noqa: F401


def test_rename_task_returns_authoritative_readback():
    task = Task(task_id="task-123")
    task.info.task_title = "Requested title"
    stub = Mock()
    stub.Task_Rename = AsyncMock(return_value=TaskRenameResponse(new_name="Stale title"))
    stub.Task_GetOneTask = AsyncMock(return_value=task)
    client = TruffleClient("127.0.0.1:80", token="token")
    client.stub = stub

    result = asyncio.run(client.rename_task("task-123", "Requested title"))

    assert result == "Requested title"
