import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
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
    repo_root = str(Path(truffile.__file__).resolve().parent.parent)
    monkeypatch.setattr(sys, "path", ["/tmp/external"])

    truffile._ensure_bundled_truffle_on_path()

    assert sys.path[0] == repo_root


def test_client_user_convo_and_clear_other_user_wrappers():
    calls = []

    class FakeStub:
        async def Client_UserIDForToken(self, req, metadata=None):
            calls.append(("identity", req, metadata))
            return SimpleNamespace(user_id="u123", username="abd")

        async def System_ClearOtherUsersData(self, req, metadata=None):
            calls.append(("clear", req, metadata))
            return SimpleNamespace(num_users_cleared=2)

        async def Convo_Reset(self, req, metadata=None):
            calls.append(("reset", req, metadata, req.hard_reset))
            return SimpleNamespace()

    client = TruffleClient("127.0.0.1:80", token="token", app_id="app")
    client.stub = FakeStub()

    identity = asyncio.run(client.get_current_user_identity())
    cleared = asyncio.run(client.clear_other_users_data())
    asyncio.run(client.reset_convo(hard=True))

    assert identity.user_id == "u123"
    assert identity.username == "abd"
    assert cleared.num_users_cleared == 2
    assert calls[0][0] == "identity"
    assert calls[0][2] == [("session", "token"), ("app-id", "app")]
    assert calls[1][0] == "clear"
    assert calls[2][0] == "reset"
    assert calls[2][3] is True
