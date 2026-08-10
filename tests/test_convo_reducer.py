import asyncio
from types import SimpleNamespace

from truffle.os.convo_pb2 import (
    ConvoNode,
    ConvoStreamUpdate,
    ConvoThreadInfo,
    GetConvoNodesResponse,
    GetConvoThreadsResponse,
    MarkConvoThreadReadResponse,
)
from truffle.os.notification_pb2 import Notification

from truffile.convo_chat import (
    ConvoChatSession,
    ConvoStateReducer,
    history_rows,
    node_reply_text,
)


def ai_node(node_id, thread_id, text):
    node = ConvoNode(id=node_id, thread_id=thread_id)
    node.ai.reply.content = text
    return node


def test_numeric_and_string_ids_normalize_to_one_node_key():
    reducer = ConvoStateReducer()
    reducer.upsert_node(SimpleNamespace(id="7", thread_id="2", value="old"))
    reducer.upsert_node(SimpleNamespace(id=7, thread_id=2, value="new"))
    assert list(reducer.nodes_by_id) == [7]
    assert reducer.nodes_by_id[7].value == "new"


def test_repeated_durable_snapshot_replaces_instead_of_appending():
    reducer = ConvoStateReducer()
    reducer.upsert_node(ai_node(4, 2, "partial"))
    reducer.upsert_node(ai_node(4, 2, "final"))
    assert len(reducer.nodes_by_id) == 1
    assert node_reply_text(reducer.nodes_by_id[4]) == "final"


def test_reply_and_thought_deltas_accumulate_then_durable_clears_them():
    reducer = ConvoStateReducer()
    for reply, thought in [("hel", "rea"), ("lo", "son")]:
        update = ConvoStreamUpdate()
        agent = update.agent_updates.add(node_id=9, block_id=1)
        agent.streaming_reply_content = reply
        agent.streaming_thought_content = thought
        reducer.apply_stream_update(update)
    assert reducer.transient_blocks[(9, 1)].reply == "hello"
    assert reducer.transient_blocks[(9, 1)].thought == "reason"

    reducer.apply_stream_update(ConvoStreamUpdate(nodes=[ai_node(9, 3, "hello")]))
    assert (9, 1) not in reducer.transient_blocks


def test_tool_starts_dedupe_by_node_block_and_call_id():
    reducer = ConvoStateReducer()
    for display in ["Search", "Search again"]:
        update = ConvoStreamUpdate()
        agent = update.agent_updates.add(node_id=9, block_id=2)
        agent.tool_call_start.tool_call_id = "call-1"
        agent.tool_call_start.display_name = display
        reducer.apply_stream_update(update)
    assert len(reducer.transient_tool_starts) == 1


def test_durable_agent_blocks_render_in_block_order_with_tools_and_thoughts():
    node = ai_node(20, 4, "root")
    child = node.ai.sub_blocks.add(block_id=2)
    child.reply.content = " child"
    child.thoughts.add(content="thinking")
    child.tool_calls.add(tool_name="lookup")
    rows = history_rows([node])
    assert rows[0]["content"] == "root child"
    assert rows[0]["thinking"] == ["thinking"]
    assert rows[0]["tool_calls"] == ["lookup"]


def test_thread_index_pins_main_sorts_nodes_and_filters_hidden_system_rows():
    reducer = ConvoStateReducer()
    older = ConvoThreadInfo(thread_id=2, display_name="Older", thread_kind="NODE", latest_node_id=10)
    older.latest_node.created_at.seconds = 100
    newer = ConvoThreadInfo(thread_id=3, display_name="Newer", thread_kind="NODE", latest_node_id=11)
    newer.latest_node.created_at.seconds = 200
    reducer.upsert_threads(
        [
            older,
            newer,
            ConvoThreadInfo(thread_id=-1, display_name="Activity", thread_kind="SYSTEM"),
            ConvoThreadInfo(thread_id=8, display_name="Bulletin", thread_kind="BULLETIN"),
        ]
    )
    visible = reducer.visible_threads(hidden_thread_ids={2})
    assert [thread.thread_id for thread in visible] == [0, 3]
    assert reducer.visible_threads(hidden_thread_ids={2}, include_hidden=True)[1].thread_id == 3


def test_history_covers_user_error_system_forward_and_interaction_fallbacks():
    user = ConvoNode(id=1, thread_id=0)
    user.user.content = "hello"
    error = ConvoNode(id=2, thread_id=0)
    error.error.error = "boom"
    system = ConvoNode(id=3, thread_id=0)
    system.system.inbox_event.content = "runtime event"
    forward = ConvoNode(id=4, thread_id=0)
    forward.forward.source_label = "Inbox"
    forward.forward.user_response.content = "forwarded text"
    setup = ConvoNode(id=5, thread_id=0)
    setup.setup.title = "Connect account"
    action = ConvoNode(id=6, thread_id=0)
    action.action.title = "Approve action"
    rows = history_rows([user, error, system, forward, setup, action])
    assert [row["kind"] for row in rows] == ["user", "error", "system", "forward", "setup", "action"]
    assert "supported client" in rows[-1]["content"]


class QueueStream:
    def __init__(self, items=()):
        self.queue = asyncio.Queue()
        for item in items:
            self.queue.put_nowait(item)

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.queue.get()
        if item is StopAsyncIteration:
            raise StopAsyncIteration
        return item


def test_bootstrap_replays_buffered_live_snapshot_after_older_query():
    async def scenario():
        ready = Notification(type=Notification.SESSION_READY)
        notifications = QueueStream([ready])
        live = ConvoStreamUpdate(nodes=[ai_node(10, 5, "new live")])
        convo = QueueStream([live])

        class Client:
            def subscribe_to_notifications(self):
                return notifications

            def open_convo_stream(self):
                return convo

            async def get_convo_threads(self, **_kwargs):
                await asyncio.sleep(0.01)
                return GetConvoThreadsResponse(
                    threads=[ConvoThreadInfo(thread_id=5, thread_kind="NODE")]
                )

            async def get_convo_nodes(self, *_args, **_kwargs):
                return GetConvoNodesResponse(nodes=[ai_node(10, 5, "old query")])

            async def mark_convo_thread_read(self, *_args, **_kwargs):
                return MarkConvoThreadReadResponse(
                    thread=ConvoThreadInfo(thread_id=5, thread_kind="NODE")
                )

        session = ConvoChatSession(Client())
        await session.start(selected_thread_id=5)
        try:
            assert node_reply_text(session.reducer.nodes_by_id[10]) == "new live"
        finally:
            await session.close()

    asyncio.run(scenario())
