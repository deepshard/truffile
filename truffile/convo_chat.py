"""Convo-backed chat state, streaming, and completion fencing.

This module intentionally has no terminal UI.  The CLI owns presentation while
this layer owns the two session-long streams and all Convo wire semantics.
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import time
import uuid
from dataclasses import dataclass, field
from datetime import timezone
from typing import Any, Callable, Iterable

import grpc
from truffle.os.convo_pb2 import ConvoThreadInfo
from truffle.os.notification_pb2 import Notification


class ConvoChatError(RuntimeError):
    """Base error for a Convo chat session."""


class ConvoUnavailableError(ConvoChatError):
    """The connected firmware does not expose the required Convo API."""


class CompletionFenceLostError(ConvoChatError):
    """The notification completion fence disconnected during a turn."""


class ThreadSelectionError(ConvoChatError):
    """A requested thread does not exist or is not user-visible."""


def _clone_message(message: Any) -> Any:
    if hasattr(message, "CopyFrom"):
        cloned = message.__class__()
        cloned.CopyFrom(message)
        return cloned
    return copy.deepcopy(message)


def _has_field(message: Any, name: str) -> bool:
    has_field = getattr(message, "HasField", None)
    if callable(has_field):
        try:
            return bool(has_field(name))
        except (ValueError, TypeError):
            pass
    value = getattr(message, name, None)
    if value is None:
        return False
    if isinstance(value, (str, bytes, list, tuple, dict, set)):
        return bool(value)
    return True


def node_kind(node: Any) -> str:
    which_oneof = getattr(node, "WhichOneof", None)
    if callable(which_oneof):
        try:
            kind = which_oneof("block")
            if kind:
                return str(kind)
        except (ValueError, TypeError):
            pass
    for kind in ("user", "ai", "system", "error", "forward", "action", "setup"):
        if _has_field(node, kind):
            return kind
    return "unknown"


def _timestamp_iso(message: Any, field: str) -> str:
    if not _has_field(message, field):
        return ""
    stamp = getattr(message, field)
    try:
        value = stamp.ToDatetime(tzinfo=timezone.utc)
        return value.isoformat()
    except (AttributeError, TypeError, ValueError):
        seconds = int(getattr(stamp, "seconds", 0) or 0)
        nanos = int(getattr(stamp, "nanos", 0) or 0)
        return f"{seconds:020d}.{nanos:09d}" if seconds or nanos else ""


def _timestamp_key(message: Any, field: str) -> tuple[int, int]:
    if not _has_field(message, field):
        return (0, 0)
    stamp = getattr(message, field)
    return (int(getattr(stamp, "seconds", 0) or 0), int(getattr(stamp, "nanos", 0) or 0))


@dataclass
class TransientBlock:
    reply: str = ""
    thought: str = ""


@dataclass(frozen=True)
class ConvoLiveEvent:
    kind: str
    node_id: int
    block_id: int
    content: str = ""
    tool_call_id: str = ""
    thread_id: int | None = None


@dataclass
class ConvoTurnResult:
    thread_id: int
    user_node_id: int
    title: str
    content: str = ""
    thinking: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    pending_user_response: bool = False
    status: str = "ok"
    error: str | None = None
    interrupted: bool = False
    timed_out: bool = False


class ConvoStateReducer:
    """Reducer for durable Convo state and transient agent block deltas."""

    def __init__(self) -> None:
        self.nodes_by_id: dict[int, Any] = {}
        self.threads_by_id: dict[int, Any] = {}
        self.transient_blocks: dict[tuple[int, int], TransientBlock] = {}
        self.transient_tool_starts: dict[tuple[int, int, str], Any] = {}
        self.convo_info: Any | None = None
        self.stream_errors: list[str] = []

    def upsert_node(self, node: Any) -> None:
        node_id = int(getattr(node, "id"))
        self.nodes_by_id[node_id] = _clone_message(node)
        for key in [key for key in self.transient_blocks if key[0] == node_id]:
            self.transient_blocks.pop(key, None)
        for key in [key for key in self.transient_tool_starts if key[0] == node_id]:
            self.transient_tool_starts.pop(key, None)

    def upsert_nodes(self, nodes: Iterable[Any]) -> None:
        for node in nodes:
            self.upsert_node(node)

    def upsert_thread(self, thread: Any) -> None:
        self.threads_by_id[int(getattr(thread, "thread_id"))] = _clone_message(thread)

    def upsert_threads(self, threads: Iterable[Any]) -> None:
        for thread in threads:
            self.upsert_thread(thread)

    def apply_stream_update(self, update: Any) -> list[ConvoLiveEvent]:
        events: list[ConvoLiveEvent] = []
        durable_ids = {int(getattr(node, "id")) for node in getattr(update, "nodes", [])}

        for agent_update in getattr(update, "agent_updates", []):
            node_id = int(getattr(agent_update, "node_id"))
            if node_id in durable_ids:
                continue
            block_id = int(getattr(agent_update, "block_id"))
            key = (node_id, block_id)
            transient = self.transient_blocks.setdefault(key, TransientBlock())
            thread_id = None
            durable_node = self.nodes_by_id.get(node_id)
            if durable_node is not None:
                thread_id = int(getattr(durable_node, "thread_id"))

            reply = str(getattr(agent_update, "streaming_reply_content", "") or "")
            if reply:
                transient.reply += reply
                events.append(ConvoLiveEvent("reply", node_id, block_id, reply, thread_id=thread_id))

            thought = str(getattr(agent_update, "streaming_thought_content", "") or "")
            if thought:
                transient.thought += thought
                events.append(ConvoLiveEvent("thought", node_id, block_id, thought, thread_id=thread_id))

            if _has_field(agent_update, "tool_call_start"):
                tool = getattr(agent_update, "tool_call_start")
                tool_call_id = str(getattr(tool, "tool_call_id", "") or "")
                tool_key = (node_id, block_id, tool_call_id)
                if tool_key not in self.transient_tool_starts:
                    self.transient_tool_starts[tool_key] = _clone_message(tool)
                    display = str(
                        getattr(tool, "display_name", "")
                        or getattr(tool, "tool_name", "")
                        or "tool"
                    )
                    events.append(
                        ConvoLiveEvent(
                            "tool",
                            node_id,
                            block_id,
                            display,
                            tool_call_id=tool_call_id,
                            thread_id=thread_id,
                        )
                    )

        self.upsert_nodes(getattr(update, "nodes", []))
        self.upsert_threads(getattr(update, "threads", []))
        if _has_field(update, "convo_info"):
            self.convo_info = _clone_message(getattr(update, "convo_info"))
        if _has_field(update, "error"):
            message = str(getattr(getattr(update, "error"), "error", "") or "Convo stream error")
            self.stream_errors.append(message)
            events.append(ConvoLiveEvent("error", 0, 0, message))
        return events

    def thread_nodes(self, thread_id: int) -> list[Any]:
        wanted = int(thread_id)
        return sorted(
            (
                node
                for node in self.nodes_by_id.values()
                if int(getattr(node, "thread_id")) == wanted
            ),
            key=lambda node: int(getattr(node, "id")),
        )

    def visible_threads(
        self,
        *,
        hidden_thread_ids: set[int] | None = None,
        include_hidden: bool = False,
    ) -> list[Any]:
        hidden = hidden_thread_ids or set()
        main = self.threads_by_id.get(0)
        if main is None:
            main = ConvoThreadInfo(thread_id=0, display_name="Main", thread_kind="MAIN")

        side_threads = []
        for thread_id, thread in self.threads_by_id.items():
            kind = str(getattr(thread, "thread_kind", "") or "").upper()
            if thread_id in (0, -1) or kind != "NODE":
                continue
            if thread_id in hidden and not include_hidden:
                continue
            side_threads.append(thread)

        def sort_key(thread: Any) -> tuple[int, int, int]:
            latest = getattr(thread, "latest_node", None)
            seconds, nanos = _timestamp_key(latest, "created_at") if latest is not None else (0, 0)
            latest_id = int(getattr(thread, "latest_node_id", 0) or 0)
            return (seconds, nanos, latest_id)

        side_threads.sort(key=sort_key, reverse=True)
        return [main, *side_threads]

    def title_for_thread(self, thread_id: int) -> str:
        thread = self.threads_by_id.get(int(thread_id))
        title = str(getattr(thread, "display_name", "") or "") if thread else ""
        if title:
            return title
        return "Main" if int(thread_id) == 0 else "Untitled chat"


def _flatten_agent_blocks(block: Any) -> list[Any]:
    blocks = [block]
    for child in getattr(block, "sub_blocks", []):
        blocks.extend(_flatten_agent_blocks(child))
    return sorted(blocks, key=lambda item: int(getattr(item, "block_id", 0) or 0))


def node_reply_text(node: Any) -> str:
    if node_kind(node) != "ai":
        return ""
    parts: list[str] = []
    for block in _flatten_agent_blocks(getattr(node, "ai")):
        if _has_field(block, "reply"):
            content = str(getattr(getattr(block, "reply"), "content", "") or "")
            if content:
                parts.append(content)
    return "".join(parts).strip()


def node_thoughts(node: Any) -> list[str]:
    if node_kind(node) != "ai":
        return []
    result: list[str] = []
    for block in _flatten_agent_blocks(getattr(node, "ai")):
        for thought in getattr(block, "thoughts", []):
            content = str(getattr(thought, "content", "") or "")
            if content:
                result.append(content)
    return result


def node_tool_calls(node: Any) -> list[str]:
    if node_kind(node) != "ai":
        return []
    result: list[str] = []
    for block in _flatten_agent_blocks(getattr(node, "ai")):
        for tool in getattr(block, "tool_calls", []):
            name = str(getattr(tool, "tool_name", "") or "tool")
            if name not in result:
                result.append(name)
    return result


def node_display_text(node: Any) -> str:
    kind = node_kind(node)
    if kind == "user":
        return str(getattr(getattr(node, "user"), "content", "") or "")
    if kind == "ai":
        return node_reply_text(node)
    if kind == "error":
        return str(getattr(getattr(node, "error"), "error", "") or "Convo error")
    if kind == "forward":
        forward = getattr(node, "forward")
        source = str(getattr(forward, "source_label", "") or "forwarded")
        content = ""
        if _has_field(forward, "user_response"):
            content = str(getattr(getattr(forward, "user_response"), "content", "") or "")
        return f"{source}: {content}".strip()
    if kind == "system":
        system = getattr(node, "system")
        if _has_field(system, "inbox_event"):
            event = getattr(system, "inbox_event")
            return str(getattr(event, "content", "") or getattr(event, "title", "") or "System event")
        if _has_field(system, "system_event"):
            return str(getattr(getattr(system, "system_event"), "label", "") or "System event")
        return "System event"
    if kind in ("setup", "action"):
        block = getattr(node, kind)
        title = str(getattr(block, "title", "") or "Interaction required")
        return f"{title} — complete this interaction in a supported client."
    return ""


def _requires_interaction(node: Any) -> bool:
    kind = node_kind(node)
    if kind == "action":
        # Unspecified is treated as pending for older firmware snapshots.
        return int(getattr(getattr(node, "action"), "status", 0) or 0) in {0, 1}
    if kind == "setup":
        # PROCESSING still requires completion in a supported client.
        return int(getattr(getattr(node, "setup"), "status", 0) or 0) in {0, 1, 2}
    return False


def _reply_like(node: Any) -> bool:
    return node_kind(node) in {"ai", "error"} or _requires_interaction(node)


@dataclass
class _InFlightTurn:
    thread_id: int
    user_node_id: int
    request_id: str
    fence_lost: bool = False
    interrupted: bool = False
    timed_out: bool = False
    interrupt_deadline: float | None = None


class ConvoChatSession:
    """One authenticated user's process-long Convo chat session."""

    def __init__(
        self,
        client: Any,
        *,
        hidden_thread_ids: Iterable[int] = (),
        session_ready_timeout: float = 15.0,
    ) -> None:
        self.client = client
        self.reducer = ConvoStateReducer()
        self.selected_thread_id: int | None = None
        self.hidden_thread_ids = {int(value) for value in hidden_thread_ids}
        self.turn_lock = asyncio.Lock()
        self.session_ready_timeout = session_ready_timeout

        self._condition = asyncio.Condition()
        self._terminal_candidates: set[tuple[int, int]] = set()
        self._turn: _InFlightTurn | None = None
        self._live_callback: Callable[[ConvoLiveEvent], Any] | None = None
        self._notification_task: asyncio.Task | None = None
        self._convo_task: asyncio.Task | None = None
        self._supervisor_task: asyncio.Task | None = None
        self._reconnect_requested = asyncio.Event()
        self._ready = asyncio.Event()
        self._started = False
        self._closing = False
        self._reconnecting = False
        self._bootstrapping = False
        self._stream_buffer: list[Any] = []
        self._fatal_error: Exception | None = None

    async def start(self, *, selected_thread_id: int | None = None) -> None:
        try:
            notification_iterator = await self._open_ready_notifications()
            convo_iterator = self.client.open_convo_stream().__aiter__()
        except Exception as exc:
            raise self._connection_error(exc) from exc

        self._bootstrapping = True
        self._notification_task = asyncio.create_task(
            self._consume_notifications(notification_iterator), name="convo-notifications"
        )
        self._convo_task = asyncio.create_task(
            self._consume_convo(convo_iterator), name="convo-stream"
        )
        try:
            await self.refresh_threads()
            if selected_thread_id is not None:
                await self._load_thread(int(selected_thread_id), mark_read=True)
                self.selected_thread_id = int(selected_thread_id)
        except Exception as exc:
            await self.close()
            raise self._connection_error(exc) from exc
        finally:
            self._bootstrapping = False

        buffered, self._stream_buffer = self._stream_buffer, []
        for update in buffered:
            await self.handle_stream_update(update)
        self._started = True
        self._ready.set()
        self._supervisor_task = asyncio.create_task(
            self._supervise_reconnects(), name="convo-reconnect-supervisor"
        )

    async def _open_ready_notifications(self):
        stream = self.client.subscribe_to_notifications()
        iterator = stream.__aiter__()
        try:
            first = await asyncio.wait_for(
                iterator.__anext__(), timeout=self.session_ready_timeout
            )
        except StopAsyncIteration as exc:
            raise ConvoUnavailableError("notification stream closed before SESSION_READY") from exc
        if int(getattr(first, "type", -1)) != int(Notification.SESSION_READY):
            raise ConvoUnavailableError(
                "notification stream did not begin with SESSION_READY"
            )
        return iterator

    @staticmethod
    def _connection_error(exc: Exception) -> Exception:
        code = getattr(exc, "code", None)
        if callable(code):
            try:
                if code() == grpc.StatusCode.UNIMPLEMENTED:
                    return ConvoUnavailableError(
                        "this firmware does not support Convo chat; update the device firmware"
                    )
            except Exception:
                pass
        if isinstance(exc, ConvoChatError):
            return exc
        return ConvoUnavailableError(f"could not start Convo chat: {exc}")

    async def _consume_notifications(self, iterator: Any) -> None:
        try:
            async for notification in iterator:
                await self.handle_notification(notification)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._fatal_error = exc
        finally:
            if not self._closing and not self._reconnecting:
                await self._streams_disconnected()

    async def _consume_convo(self, iterator: Any) -> None:
        try:
            async for update in iterator:
                if self._bootstrapping:
                    self._stream_buffer.append(_clone_message(update))
                else:
                    await self.handle_stream_update(update)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._fatal_error = exc
        finally:
            if not self._closing and not self._reconnecting:
                await self._streams_disconnected()

    async def _streams_disconnected(self) -> None:
        self._ready.clear()
        if self._turn is not None:
            self._turn.fence_lost = True
        self._reconnect_requested.set()
        await self._signal()

    async def _supervise_reconnects(self) -> None:
        try:
            while not self._closing:
                await self._reconnect_requested.wait()
                self._reconnect_requested.clear()
                if self._closing:
                    return
                self._reconnecting = True
                for task in (self._notification_task, self._convo_task):
                    if task is not None and not task.done():
                        task.cancel()
                for task in (self._notification_task, self._convo_task):
                    if task is not None:
                        try:
                            await task
                        except (asyncio.CancelledError, Exception):
                            pass

                last_error: Exception | None = None
                for delay in (0.25, 0.5, 1.0, 2.0, 4.0):
                    if self._closing:
                        return
                    try:
                        await asyncio.sleep(delay)
                        notification_iterator = await self._open_ready_notifications()
                        convo_iterator = self.client.open_convo_stream().__aiter__()
                        self._bootstrapping = True
                        self._notification_task = asyncio.create_task(
                            self._consume_notifications(notification_iterator),
                            name="convo-notifications",
                        )
                        self._convo_task = asyncio.create_task(
                            self._consume_convo(convo_iterator), name="convo-stream"
                        )
                        await self.refresh_threads()
                        if self.selected_thread_id is not None:
                            await self._load_thread(self.selected_thread_id, mark_read=False)
                        self._bootstrapping = False
                        buffered, self._stream_buffer = self._stream_buffer, []
                        for update in buffered:
                            await self.handle_stream_update(update)
                        self._fatal_error = None
                        self._ready.set()
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                        self._bootstrapping = False
                self._reconnecting = False
                if last_error is not None:
                    self._fatal_error = self._connection_error(last_error)
                    await self._signal()
        except asyncio.CancelledError:
            return

    async def handle_stream_update(self, update: Any) -> None:
        events = self.reducer.apply_stream_update(update)
        callback = self._live_callback
        turn = self._turn
        if callback is not None and turn is not None:
            for event in events:
                node = self.reducer.nodes_by_id.get(event.node_id)
                thread_id = event.thread_id
                if thread_id is None and node is not None:
                    thread_id = int(getattr(node, "thread_id"))
                if (
                    event.kind == "error"
                    or (
                        thread_id == turn.thread_id
                        and event.node_id > turn.user_node_id
                    )
                ):
                    result = callback(event)
                    if inspect.isawaitable(result):
                        await result
        await self._signal()

    async def handle_notification(self, notification: Any) -> None:
        notification_type = int(getattr(notification, "type", -1))
        if notification_type == int(Notification.SERVER_CLOSING):
            await self._streams_disconnected()
            return
        if notification_type != int(Notification.CONVO_UPDATE):
            return
        payload = getattr(notification, "convo_update_notification", None)
        if payload is None:
            return
        for node in getattr(payload, "nodes", []):
            if _reply_like(node):
                self._terminal_candidates.add(
                    (int(getattr(node, "thread_id")), int(getattr(node, "id")))
                )
        await self._signal()

    async def _signal(self) -> None:
        async with self._condition:
            self._condition.notify_all()

    async def refresh_threads(self) -> list[Any]:
        response = await self.client.get_convo_threads(
            include_system_threads=False,
            include_latest_nodes=True,
            include_anchor_nodes=True,
        )
        self.reducer.upsert_threads(getattr(response, "threads", []))
        if _has_field(response, "convo_info"):
            self.reducer.convo_info = _clone_message(getattr(response, "convo_info"))
        return self.visible_threads()

    def visible_threads(self, *, include_hidden: bool = False) -> list[Any]:
        return self.reducer.visible_threads(
            hidden_thread_ids=self.hidden_thread_ids,
            include_hidden=include_hidden,
        )

    def thread_rows(self, *, include_hidden: bool = False) -> list[dict[str, Any]]:
        rows = []
        for thread in self.visible_threads(include_hidden=include_hidden):
            thread_id = int(getattr(thread, "thread_id"))
            anchor = getattr(thread, "anchor_node", None)
            latest = getattr(thread, "latest_node", None)
            rows.append(
                {
                    "thread_id": str(thread_id),
                    "task_id": str(thread_id),
                    "title": self.reducer.title_for_thread(thread_id),
                    "thread_kind": str(getattr(thread, "thread_kind", "") or ("MAIN" if thread_id == 0 else "NODE")),
                    "created": _timestamp_iso(anchor, "created_at") if anchor is not None else "",
                    "updated": _timestamp_iso(latest, "created_at") if latest is not None else "",
                    "latest_node_id": str(int(getattr(thread, "latest_node_id", 0) or 0)),
                    "last_read_node_id": str(int(getattr(thread, "last_read_node_id", 0) or 0)),
                    "unread_count": int(getattr(thread, "unread_count", 0) or 0),
                    "has_unread": bool(getattr(thread, "has_unread", False)),
                    "hidden_local": thread_id in self.hidden_thread_ids,
                }
            )
        return rows

    def resolve_thread(self, selector: str | int, *, include_hidden: bool = False) -> int:
        raw = str(selector).strip()
        if not raw:
            raise ThreadSelectionError("thread selector is empty")
        if raw.lstrip("-").isdigit():
            thread_id = int(raw)
            visible_ids = {
                int(getattr(thread, "thread_id"))
                for thread in self.visible_threads(include_hidden=include_hidden)
            }
            if thread_id not in visible_ids:
                raise ThreadSelectionError(f"Convo thread {thread_id} was not found")
            return thread_id

        matches = [
            int(getattr(thread, "thread_id"))
            for thread in self.visible_threads(include_hidden=include_hidden)
            if self.reducer.title_for_thread(int(getattr(thread, "thread_id"))).casefold()
            == raw.casefold()
        ]
        if not matches:
            raise ThreadSelectionError(f'Convo thread named "{raw}" was not found')
        if len(matches) > 1:
            raise ThreadSelectionError(
                f'more than one Convo thread is named "{raw}"; use --thread-id'
            )
        return matches[0]

    def latest_thread_id(self, *, include_hidden: bool = False) -> int:
        threads = self.visible_threads(include_hidden=include_hidden)
        if not threads:
            raise ThreadSelectionError("no Convo threads are available")
        return max(
            (int(getattr(thread, "thread_id")) for thread in threads),
            key=lambda thread_id: int(
                getattr(self.reducer.threads_by_id.get(thread_id), "latest_node_id", 0) or 0
            ),
        )

    async def _load_thread(self, thread_id: int, *, mark_read: bool) -> list[Any]:
        response = await self.client.get_convo_nodes(
            int(thread_id), target_node_id=0, max_before=50, max_after=0
        )
        self.reducer.upsert_nodes(getattr(response, "nodes", []))
        if _has_field(response, "convo_info"):
            self.reducer.convo_info = _clone_message(getattr(response, "convo_info"))
        if mark_read:
            read_response = await self.client.mark_convo_thread_read(
                int(thread_id), through_node_id=0
            )
            if _has_field(read_response, "thread"):
                self.reducer.upsert_thread(getattr(read_response, "thread"))
        return self.reducer.thread_nodes(int(thread_id))

    async def select_thread(self, thread_id: int, *, include_hidden: bool = False) -> list[Any]:
        resolved = self.resolve_thread(str(thread_id), include_hidden=include_hidden)
        nodes = await self._load_thread(resolved, mark_read=True)
        self.selected_thread_id = resolved
        return nodes

    def new_thread(self) -> None:
        self.selected_thread_id = None

    async def rename_selected(self, display_name: str) -> Any:
        if self.selected_thread_id is None:
            raise ThreadSelectionError("send a message before renaming a new thread")
        name = display_name.strip()
        if not name:
            raise ValueError("thread name cannot be empty")
        response = await self.client.rename_convo_thread(self.selected_thread_id, name)
        if _has_field(response, "thread"):
            self.reducer.upsert_thread(getattr(response, "thread"))
        return response

    def hide_thread(self, thread_id: int) -> None:
        thread_id = int(thread_id)
        if thread_id in (0, -1):
            raise ThreadSelectionError("Main and system threads cannot be hidden")
        self.hidden_thread_ids.add(thread_id)
        if self.selected_thread_id == thread_id:
            self.selected_thread_id = None

    def restore_thread(self, thread_id: int) -> None:
        self.hidden_thread_ids.discard(int(thread_id))

    async def send(
        self,
        message: str,
        *,
        timeout: float | None = None,
        on_live_event: Callable[[ConvoLiveEvent], Any] | None = None,
    ) -> ConvoTurnResult:
        content = message.strip()
        if not content:
            raise ValueError("message cannot be empty")
        async with self.turn_lock:
            if self._started:
                while not self._ready.is_set():
                    if self._fatal_error is not None:
                        raise self._connection_error(self._fatal_error)
                    async with self._condition:
                        await self._condition.wait()
            if self._fatal_error is not None:
                raise self._connection_error(self._fatal_error)
            draft = self.selected_thread_id is None
            target_thread_id = 0 if draft else int(self.selected_thread_id)
            request_id = str(uuid.uuid4())
            self._live_callback = on_live_event
            response = await self.client.send_convo_user_response(
                content,
                target_thread_id=target_thread_id,
                agent_should_respond_in_subthread=draft,
                request_id=request_id,
            )
            node = getattr(response, "node")
            self.reducer.upsert_node(node)
            user_node_id = int(getattr(node, "id"))
            if draft:
                if not _has_field(node, "child_thread"):
                    self._live_callback = None
                    raise ConvoChatError(
                        "Convo accepted the opening message but did not return a child thread"
                    )
                reply_thread_id = int(getattr(getattr(node, "child_thread"), "thread_id"))
                self.selected_thread_id = reply_thread_id
                if reply_thread_id not in self.reducer.threads_by_id:
                    self.reducer.upsert_thread(
                        ConvoThreadInfo(
                            thread_id=reply_thread_id,
                            thread_kind="NODE",
                            display_name="Untitled chat",
                            anchor_node_id=user_node_id,
                        )
                    )
            else:
                reply_thread_id = target_thread_id

            turn = _InFlightTurn(reply_thread_id, user_node_id, request_id)
            self._turn = turn
            try:
                if timeout is None:
                    result = await self._wait_for_settlement(turn)
                else:
                    if timeout <= 0:
                        raise ValueError("--timeout must be greater than zero")
                    try:
                        result = await asyncio.wait_for(
                            self._wait_for_settlement(turn), timeout=timeout
                        )
                    except asyncio.TimeoutError:
                        turn.timed_out = True
                        await self.request_interrupt()
                        try:
                            result = await asyncio.wait_for(
                                self._wait_for_settlement(turn, ignore_fence=True),
                                timeout=5.0,
                            )
                        except (asyncio.TimeoutError, CompletionFenceLostError):
                            await self._refresh_turn_nodes(turn)
                            result = self._build_result(turn)
                        result.timed_out = True
                        result.status = "timeout"
                        result.error = f"timed out after {timeout:g} seconds"
                result.interrupted = turn.interrupted
                return result
            finally:
                self._turn = None
                self._live_callback = None

    async def _wait_for_settlement(
        self, turn: _InFlightTurn, *, ignore_fence: bool = False
    ) -> ConvoTurnResult:
        last_refreshed_candidate = 0
        while True:
            if turn.fence_lost and not ignore_fence:
                raise CompletionFenceLostError(
                    "completion fence was lost; durable output was retained and the message was not resent"
                )
            if self._fatal_error is not None and not ignore_fence:
                raise CompletionFenceLostError(
                    "completion fence was lost; durable output was retained and the message was not resent"
                )

            candidates = sorted(
                node_id
                for thread_id, node_id in self._terminal_candidates
                if thread_id == turn.thread_id and node_id > turn.user_node_id
            )
            observed = self._reply_node_ids(turn)
            newest_observed = max(observed, default=0)
            newest_candidate = max(candidates, default=0)
            if newest_candidate and newest_candidate > last_refreshed_candidate:
                await self._refresh_turn_nodes(turn)
                last_refreshed_candidate = newest_candidate
                observed = self._reply_node_ids(turn)
                newest_observed = max(observed, default=0)
                if newest_observed and newest_observed in candidates:
                    return self._build_result(turn)

            if turn.interrupted and turn.interrupt_deadline is not None:
                remaining = turn.interrupt_deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    await self._refresh_turn_nodes(turn)
                    result = self._build_result(turn)
                    result.status = "interrupted"
                    result.interrupted = True
                    return result
            else:
                remaining = None

            async with self._condition:
                if remaining is None:
                    await self._condition.wait()
                else:
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=remaining)
                    except asyncio.TimeoutError:
                        pass

    def _reply_node_ids(self, turn: _InFlightTurn) -> list[int]:
        return [
            int(getattr(node, "id"))
            for node in self.reducer.thread_nodes(turn.thread_id)
            if int(getattr(node, "id")) > turn.user_node_id and _reply_like(node)
        ]

    async def _refresh_turn_nodes(self, turn: _InFlightTurn) -> None:
        response = await self.client.get_convo_nodes(
            turn.thread_id,
            target_node_id=turn.user_node_id,
            max_before=0,
            max_after=-1,
        )
        self.reducer.upsert_nodes(getattr(response, "nodes", []))
        if _has_field(response, "convo_info"):
            self.reducer.convo_info = _clone_message(getattr(response, "convo_info"))

    def _build_result(self, turn: _InFlightTurn) -> ConvoTurnResult:
        nodes = [
            node
            for node in self.reducer.thread_nodes(turn.thread_id)
            if int(getattr(node, "id")) > turn.user_node_id and _reply_like(node)
        ]
        content_parts: list[str] = []
        thinking: list[str] = []
        tools: list[str] = []
        pending = False
        status = "ok"
        error_message: str | None = None
        for node in nodes:
            kind = node_kind(node)
            if kind == "ai":
                text = node_reply_text(node)
                if text:
                    content_parts.append(text)
                thinking.extend(node_thoughts(node))
                for tool in node_tool_calls(node):
                    if tool not in tools:
                        tools.append(tool)
            elif kind == "error":
                error_message = node_display_text(node)
                status = "error"
            elif kind in ("setup", "action") and _requires_interaction(node):
                pending = True
                status = "interaction_required"
                content_parts.append(node_display_text(node))
        return ConvoTurnResult(
            thread_id=turn.thread_id,
            user_node_id=turn.user_node_id,
            title=self.reducer.title_for_thread(turn.thread_id),
            content="\n\n".join(part for part in content_parts if part),
            thinking=thinking,
            tool_calls=tools,
            pending_user_response=pending,
            status=status,
            error=error_message,
            interrupted=turn.interrupted,
            timed_out=turn.timed_out,
        )

    def latest_result(self, thread_id: int) -> ConvoTurnResult:
        nodes = [node for node in self.reducer.thread_nodes(thread_id) if _reply_like(node)]
        if not nodes:
            return ConvoTurnResult(
                thread_id=int(thread_id),
                user_node_id=0,
                title=self.reducer.title_for_thread(thread_id),
            )
        latest = nodes[-1]
        synthetic = _InFlightTurn(int(thread_id), int(getattr(latest, "id")) - 1, "")
        return self._build_result(synthetic)

    async def request_interrupt(self) -> None:
        turn = self._turn
        thread_id = turn.thread_id if turn is not None else self.selected_thread_id
        if thread_id is None:
            raise ThreadSelectionError("no active thread to interrupt")
        if turn is not None:
            turn.interrupted = True
            turn.interrupt_deadline = asyncio.get_running_loop().time() + 5.0
        await self.client.interrupt_convo(int(thread_id))
        await self._signal()
        if turn is None:
            await self._load_thread(int(thread_id), mark_read=False)

    async def close(self) -> None:
        self._closing = True
        self._ready.clear()
        tasks = [self._notification_task, self._convo_task, self._supervisor_task]
        for task in tasks:
            if task is not None and not task.done():
                task.cancel()
        for task in tasks:
            if task is not None:
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass


def history_rows(nodes: Iterable[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in sorted(nodes, key=lambda item: int(getattr(item, "id"))):
        text = node_display_text(node)
        kind = node_kind(node)
        if text or kind in {"setup", "action", "error"}:
            rows.append(
                {
                    "node_id": str(int(getattr(node, "id"))),
                    "thread_id": str(int(getattr(node, "thread_id"))),
                    "kind": kind,
                    "content": text,
                    "thinking": node_thoughts(node),
                    "tool_calls": node_tool_calls(node),
                    "created": _timestamp_iso(node, "created_at"),
                }
            )
    return rows
