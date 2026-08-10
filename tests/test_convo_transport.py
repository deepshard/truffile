import asyncio
import inspect

import pytest

from truffile.transport.client import TruffleClient
import truffile.transport.client as transport_client


class FakeStub:
    def __init__(self):
        self.calls = []

    def _record(self, name, request, metadata):
        self.calls.append((name, request, metadata))
        return type("Response", (), {})()

    async def Convo_GetThreads(self, request, metadata=None):
        return self._record("threads", request, metadata)

    async def Convo_GetNodes(self, request, metadata=None):
        return self._record("nodes", request, metadata)

    def Convo_OpenStream(self, request, metadata=None):
        return self._record("stream", request, metadata)

    def SubscribeToNotifications(self, request, metadata=None):
        return self._record("notifications", request, metadata)

    async def Convo_UserResponse(self, request, metadata=None):
        return self._record("send", request, metadata)

    async def Convo_RenameThread(self, request, metadata=None):
        return self._record("rename", request, metadata)

    async def Convo_MarkThreadRead(self, request, metadata=None):
        return self._record("read", request, metadata)

    async def Convo_Interrupt(self, request, metadata=None):
        return self._record("interrupt", request, metadata)


def connected_client():
    client = TruffleClient("device:80", "token", app_id="app")
    client.stub = FakeStub()
    return client


def test_get_threads_request_and_metadata_are_exact():
    client = connected_client()
    asyncio.run(client.get_convo_threads())
    name, request, metadata = client.stub.calls[-1]
    assert name == "threads"
    assert request.include_system_threads is False
    assert request.include_latest_nodes is True
    assert request.include_anchor_nodes is True
    assert metadata == [("session", "token"), ("app-id", "app")]


def test_get_nodes_pagination_is_exact():
    client = connected_client()
    asyncio.run(
        client.get_convo_nodes(42, target_node_id=9, max_before=0, max_after=-1)
    )
    _, request, _ = client.stub.calls[-1]
    assert (request.thread_id, request.target_node_id) == (42, 9)
    assert (request.max_before, request.max_after) == (0, -1)


def test_process_streams_are_dispatched_with_metadata():
    client = connected_client()
    client.open_convo_stream()
    client.subscribe_to_notifications()
    assert [call[0] for call in client.stub.calls] == ["stream", "notifications"]
    assert all(call[2] == [("session", "token"), ("app-id", "app")] for call in client.stub.calls)


@pytest.mark.parametrize(
    ("target", "subthread"),
    [(0, False), (17, False), (0, True)],
)
def test_user_response_routing_matrix(target, subthread):
    client = connected_client()
    asyncio.run(
        client.send_convo_user_response(
            "hello",
            target_thread_id=target,
            agent_should_respond_in_subthread=subthread,
            request_id="request-1",
        )
    )
    _, request, _ = client.stub.calls[-1]
    assert request.target_thread_id == target
    assert request.agent_should_respond_in_subthread is subthread
    assert request.user.content == "hello"
    assert request.request_id == "request-1"


def test_rename_mark_read_and_interrupt_fields_are_exact():
    client = connected_client()
    asyncio.run(client.rename_convo_thread(8, "Named thread"))
    asyncio.run(client.mark_convo_thread_read(8, through_node_id=91))
    asyncio.run(client.interrupt_convo(8))
    rename = client.stub.calls[0][1]
    read = client.stub.calls[1][1]
    interrupt = client.stub.calls[2][1]
    assert (rename.thread_id, rename.display_name) == (8, "Named thread")
    assert (read.thread_id, read.through_node_id) == (8, 91)
    assert interrupt.target_thread_id == 8


@pytest.mark.parametrize(
    ("method", "args", "kwargs"),
    [
        ("get_convo_threads", (), {}),
        ("get_convo_nodes", (1,), {}),
        ("send_convo_user_response", ("x",), {"target_thread_id": 0, "agent_should_respond_in_subthread": True, "request_id": "r"}),
        ("rename_convo_thread", (1, "x"), {}),
        ("mark_convo_thread_read", (1,), {}),
        ("interrupt_convo", (1,), {}),
    ],
)
def test_async_wrappers_reject_use_before_connection(method, args, kwargs):
    client = TruffleClient("device:80", "token")
    with pytest.raises(RuntimeError, match="not connected"):
        asyncio.run(getattr(client, method)(*args, **kwargs))


def test_stream_wrappers_reject_use_before_connection():
    client = TruffleClient("device:80", "token")
    with pytest.raises(RuntimeError, match="not connected"):
        client.open_convo_stream()
    with pytest.raises(RuntimeError, match="not connected"):
        client.subscribe_to_notifications()


def test_transport_contains_no_legacy_task_rpc_calls():
    source = inspect.getsource(transport_client)
    assert "Task_" not in source
    for method in (
        "open_task_stream",
        "respond_to_task",
        "interrupt_task",
        "get_task_infos",
        "rename_task",
        "delete_task",
        "set_task_apps",
    ):
        assert not hasattr(TruffleClient, method)
