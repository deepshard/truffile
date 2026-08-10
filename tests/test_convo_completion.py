import asyncio

from truffle.os.convo_pb2 import (
    ConvoNode,
    ConvoStreamUpdate,
    ConvoUserResponseResponse,
    GetConvoNodesResponse,
)
from truffle.os.notification_pb2 import Notification

from truffile.convo_chat import CompletionFenceLostError, ConvoChatSession


def ai_node(node_id, thread_id, text):
    node = ConvoNode(id=node_id, thread_id=thread_id)
    node.ai.reply.content = text
    return node


def terminal_notification(*nodes):
    notification = Notification(type=Notification.CONVO_UPDATE)
    for node in nodes:
        notification.convo_update_notification.nodes.add().CopyFrom(node)
    return notification


class FakeClient:
    def __init__(self, user_nodes):
        self.user_nodes = list(user_nodes)
        self.send_calls = []
        self.refresh_nodes = []
        self.refresh_calls = []
        self.refresh_hook = None
        self.interrupt_calls = []
        self.interrupt_event = asyncio.Event()

    async def send_convo_user_response(self, message, **kwargs):
        self.send_calls.append((message, kwargs))
        return ConvoUserResponseResponse(node=self.user_nodes.pop(0))

    async def get_convo_nodes(self, thread_id, **kwargs):
        self.refresh_calls.append((thread_id, kwargs))
        if self.refresh_hook is not None:
            return await self.refresh_hook(len(self.refresh_calls))
        return GetConvoNodesResponse(nodes=self.refresh_nodes)

    async def interrupt_convo(self, thread_id):
        self.interrupt_calls.append(thread_id)
        self.interrupt_event.set()
        return object()


def existing_user(node_id=100, thread_id=7):
    node = ConvoNode(id=node_id, thread_id=thread_id)
    node.user.content = "prompt"
    return node


def draft_user(node_id=100, child_thread_id=9):
    node = ConvoNode(id=node_id, thread_id=0)
    node.user.content = "prompt"
    node.child_thread.thread_id = child_thread_id
    return node


async def let_send_wait(session, message="hello"):
    task = asyncio.create_task(session.send(message))
    await asyncio.sleep(0)
    return task


def test_ack_silence_tool_and_openstream_snapshot_do_not_settle():
    async def scenario():
        client = FakeClient([existing_user()])
        session = ConvoChatSession(client)
        session.selected_thread_id = 7
        task = await let_send_wait(session)
        assert not task.done()

        tool_update = ConvoStreamUpdate()
        tool = tool_update.agent_updates.add(node_id=101, block_id=1).tool_call_start
        tool.tool_call_id = "tool-1"
        tool.display_name = "Search."
        await session.handle_stream_update(tool_update)
        await session.handle_stream_update(
            ConvoStreamUpdate(nodes=[ai_node(101, 7, "Done.")])
        )
        await asyncio.sleep(0)
        assert not task.done()

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())


def test_unrelated_older_and_other_thread_notifications_do_not_settle():
    async def scenario():
        client = FakeClient([existing_user()])
        session = ConvoChatSession(client)
        session.selected_thread_id = 7
        task = await let_send_wait(session)
        await session.handle_notification(
            terminal_notification(ai_node(99, 7, "old"), ai_node(101, 8, "other"))
        )
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())


def test_terminal_candidate_plus_matching_refresh_settles():
    async def scenario():
        reply = ai_node(101, 7, "final")
        client = FakeClient([existing_user()])
        client.refresh_nodes = [reply]
        session = ConvoChatSession(client)
        session.selected_thread_id = 7
        task = await let_send_wait(session)
        await session.handle_stream_update(ConvoStreamUpdate(nodes=[reply]))
        await session.handle_notification(terminal_notification(reply))
        result = await asyncio.wait_for(task, 1)
        assert result.content == "final"
        assert client.refresh_calls[0] == (
            7,
            {"target_node_id": 100, "max_before": 0, "max_after": -1},
        )

    asyncio.run(scenario())


def test_context_split_waits_for_newest_candidate_and_joins_nodes():
    async def scenario():
        first = ai_node(101, 7, "part one")
        second = ai_node(102, 7, "part two")
        refresh_started = asyncio.Event()
        release_first_refresh = asyncio.Event()
        client = FakeClient([existing_user()])

        async def refresh(call_number):
            if call_number == 1:
                refresh_started.set()
                await release_first_refresh.wait()
                return GetConvoNodesResponse(nodes=[first])
            return GetConvoNodesResponse(nodes=[first, second])

        client.refresh_hook = refresh
        session = ConvoChatSession(client)
        session.selected_thread_id = 7
        task = await let_send_wait(session)
        await session.handle_stream_update(ConvoStreamUpdate(nodes=[first]))
        await session.handle_notification(terminal_notification(first))
        await asyncio.wait_for(refresh_started.wait(), 1)
        await session.handle_stream_update(ConvoStreamUpdate(nodes=[second]))
        release_first_refresh.set()
        await asyncio.sleep(0)
        assert not task.done()
        await session.handle_notification(terminal_notification(second))
        result = await asyncio.wait_for(task, 1)
        assert result.content == "part one\n\npart two"

    asyncio.run(scenario())


def test_refresh_revealing_newer_unterminalized_node_returns_to_waiting():
    async def scenario():
        first = ai_node(101, 7, "part one")
        second = ai_node(102, 7, "part two")
        client = FakeClient([existing_user()])
        client.refresh_nodes = [first, second]
        session = ConvoChatSession(client)
        session.selected_thread_id = 7
        task = await let_send_wait(session)
        await session.handle_stream_update(ConvoStreamUpdate(nodes=[first]))
        await session.handle_notification(terminal_notification(first))
        await asyncio.sleep(0.01)
        assert not task.done()
        await session.handle_notification(terminal_notification(second))
        result = await asyncio.wait_for(task, 1)
        assert "part two" in result.content

    asyncio.run(scenario())


def test_error_and_setup_candidates_settle_with_specific_status():
    async def settle(node):
        client = FakeClient([existing_user()])
        client.refresh_nodes = [node]
        session = ConvoChatSession(client)
        session.selected_thread_id = 7
        task = await let_send_wait(session)
        await session.handle_notification(terminal_notification(node))
        return await asyncio.wait_for(task, 1)

    error_node = ConvoNode(id=101, thread_id=7)
    error_node.error.error = "runtime failed"
    error_result = asyncio.run(settle(error_node))
    assert error_result.status == "error"
    assert error_result.error == "runtime failed"

    setup_node = ConvoNode(id=101, thread_id=7)
    setup_node.setup.title = "Connect account"
    setup_result = asyncio.run(settle(setup_node))
    assert setup_result.status == "interaction_required"
    assert setup_result.pending_user_response is True
    assert "supported client" in setup_result.content


def test_new_draft_uses_main_ack_cursor_and_child_reply_thread():
    async def scenario():
        reply = ai_node(101, 9, "child reply")
        client = FakeClient([draft_user()])
        client.refresh_nodes = [reply]
        session = ConvoChatSession(client)
        task = await let_send_wait(session)
        await session.handle_notification(terminal_notification(reply))
        result = await asyncio.wait_for(task, 1)
        assert result.thread_id == 9
        assert session.selected_thread_id == 9
        _, kwargs = client.send_calls[0]
        assert kwargs["target_thread_id"] == 0
        assert kwargs["agent_should_respond_in_subthread"] is True
        assert client.refresh_calls[0][1]["target_node_id"] == 100

    asyncio.run(scenario())


def test_turn_lock_queues_second_send_until_first_settles():
    async def scenario():
        first_reply = ai_node(101, 7, "first")
        second_reply = ai_node(201, 7, "second")
        client = FakeClient([existing_user(100), existing_user(200)])
        session = ConvoChatSession(client)
        session.selected_thread_id = 7
        first = await let_send_wait(session, "one")
        second = asyncio.create_task(session.send("two"))
        await asyncio.sleep(0)
        assert len(client.send_calls) == 1

        client.refresh_nodes = [first_reply]
        await session.handle_notification(terminal_notification(first_reply))
        await asyncio.wait_for(first, 1)
        for _ in range(10):
            if len(client.send_calls) == 2:
                break
            await asyncio.sleep(0)
        assert len(client.send_calls) == 2
        client.refresh_nodes = [first_reply, second_reply]
        await session.handle_notification(terminal_notification(second_reply))
        result = await asyncio.wait_for(second, 1)
        assert result.content == "second"

    asyncio.run(scenario())


def test_timeout_interrupts_and_returns_partial_with_exit_semantics():
    async def scenario():
        reply = ai_node(101, 7, "partial")
        client = FakeClient([existing_user()])
        session = ConvoChatSession(client)
        session.selected_thread_id = 7

        async def finish_after_interrupt():
            await client.interrupt_event.wait()
            client.refresh_nodes = [reply]
            await session.handle_notification(terminal_notification(reply))

        feeder = asyncio.create_task(finish_after_interrupt())
        result = await session.send("slow", timeout=0.01)
        await feeder
        assert client.interrupt_calls == [7]
        assert result.timed_out is True
        assert result.status == "timeout"
        assert result.content == "partial"

    asyncio.run(scenario())


def test_notification_loss_during_turn_is_fence_lost_and_never_resends():
    async def scenario():
        client = FakeClient([existing_user()])
        session = ConvoChatSession(client)
        session.selected_thread_id = 7
        task = await let_send_wait(session)
        await session._streams_disconnected()
        try:
            await asyncio.wait_for(task, 1)
        except CompletionFenceLostError as exc:
            assert "not resent" in str(exc)
        else:
            raise AssertionError("send unexpectedly settled")
        assert len(client.send_calls) == 1

    asyncio.run(scenario())
