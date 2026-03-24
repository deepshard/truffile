import asyncio
import sys
from unittest.mock import Mock

import truffile
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
    repo_root = "/Users/truffle/work/truffile"
    monkeypatch.setattr(sys, "path", ["/tmp/external"])

    truffile._ensure_bundled_truffle_on_path()

    assert sys.path[0] == repo_root
