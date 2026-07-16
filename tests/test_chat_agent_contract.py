import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from truffle.os.task_actions_pb2 import TaskStreamUpdate
from truffle.os.task_pb2 import TaskInfo
from truffle.os.task_queries_pb2 import GetTaskInfosResponse

from truffile.cli.chat import TaskState, _print_update, _run_oneshot_chat, _stream_task
from truffile.storage import StoredState
from truffile.transport.client import TruffleClient


class FakeStorage:
    def __init__(self) -> None:
        self.state = StoredState(last_used_device="truffle-1234")

    def get_token(self, _device: str) -> str:
        return "token"

    def app_id_for_device(self, _device: str) -> None:
        return None


class FakeTaskClient:
    def __init__(self, *_args, **_kwargs) -> None:
        self.interrupted: list[str] = []

    async def connect(self) -> None:
        pass

    async def check_auth(self) -> bool:
        return True

    def open_task_stream(self, _prompt: str, *, app_uuids=None):
        async def updates():
            update = TaskStreamUpdate()
            update.task_id = "task-1"
            update.info.task_title = "Agent task"
            update.info.run_state = TaskInfo.TASK_RUN_STATE_READY
            node = update.nodes.add()
            node.id = 1
            node.step.thinking.cot_summaries.append("private summary")
            call = node.step.tool_calls.add()
            call.tool_name = "sensitive_tool"
            call.summary = "full detail"
            node.step.results.content = "0123456789abcdefghij"
            yield update

        return updates()

    async def interrupt_task(self, task_id: str) -> None:
        self.interrupted.append(task_id)

    async def close(self) -> None:
        pass


class RejectedTaskClient(FakeTaskClient):
    async def check_auth(self) -> bool:
        return False


class CompletedTaskClient(FakeTaskClient):
    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__()
        self.new_prompts: list[str] = []

    def open_existing_task_stream(self, task_id: str):
        async def updates():
            update = TaskStreamUpdate()
            update.task_id = task_id
            update.info.task_title = "Completed task"
            update.info.run_state = TaskInfo.TASK_RUN_STATE_READY
            node = update.nodes.add()
            node.step.results.content = "previous result"
            yield update

        return updates()

    def open_task_stream(self, prompt: str, *, app_uuids=None):
        self.new_prompts.append(prompt)
        return super().open_task_stream(prompt, app_uuids=app_uuids)


async def _resolved(_storage, *, quiet=False):
    return "truffle-1234", "192.0.2.10"


def _chat_args(**overrides):
    values = {
        "quiet": True,
        "json": True,
        "timeout": 1.0,
        "list_apps": False,
        "list_tasks": None,
        "app": None,
        "task_id": None,
        "resume_last": False,
        "prompt_words": ["hello"],
        "prompt_file": None,
        "stdin": False,
        "include_thinking": False,
        "include_tools": False,
        "full": False,
        "show_thinking": False,
        "max_output_bytes": 10,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _json_stdout(capsys) -> dict:
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_replayed_user_response_is_cleared_by_later_user_message():
    update = TaskStreamUpdate()
    pending = update.nodes.add()
    pending.id = 10
    pending.step.user_response.node_id = 42
    response = update.nodes.add()
    response.id = 11
    response.user_msg.content = "approved"
    state = TaskState()

    _print_update(update, state, quiet=True)

    assert state.pending_node_id is None
    assert state.pending_source_node_id is None


def test_stream_task_stops_on_second_ready_update_without_waiting_for_stream_close():
    async def updates():
        initial = TaskStreamUpdate()
        initial.task_id = "task-ready"
        initial.info.run_state = TaskInfo.TASK_RUN_STATE_READY
        yield initial

        content = TaskStreamUpdate()
        content.task_id = "task-ready"
        content.streaming_step_result.partial_content = "done"
        yield content

        settled = TaskStreamUpdate()
        settled.task_id = "task-ready"
        settled.info.run_state = TaskInfo.TASK_RUN_STATE_READY
        yield settled

        await asyncio.Event().wait()

    state = TaskState()
    client = FakeTaskClient()

    timed_out = asyncio.run(asyncio.wait_for(
        _stream_task(client, updates(), state, quiet=True, timeout=None),
        timeout=0.5,
    ))

    assert timed_out is False
    assert state.task_id == "task-ready"
    assert state.run_state == "TASK_RUN_STATE_READY"


def test_completed_step_does_not_report_pending_user_response():
    update = TaskStreamUpdate()
    node = update.nodes.add()
    node.id = 3
    node.step.state = node.step.STEP_RESULT
    node.step.user_response.node_id = 3
    node.step.results.content = "Message sent"
    state = TaskState()

    _print_update(update, state, quiet=True)

    assert state.pending_node_id is None


def test_quiet_update_collects_tools_without_writing(capsys):
    update = TaskStreamUpdate()
    node = update.nodes.add()
    call = node.step.tool_calls.add()
    call.tool_name = "calendar"
    call.summary = "reading events"
    state = TaskState()

    _print_update(update, state, quiet=True)

    assert state.tool_calls == ["calendar"]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_stream_timeout_interrupts_known_task():
    class Client:
        def __init__(self) -> None:
            self.interrupted: list[str] = []

        async def interrupt_task(self, task_id: str) -> None:
            self.interrupted.append(task_id)

    async def slow_stream():
        await asyncio.sleep(1)
        if False:
            yield None

    client = Client()
    state = TaskState(task_id="task-timeout")

    timed_out = asyncio.run(_stream_task(
        client,
        slow_stream(),
        state,
        quiet=True,
        timeout=0.01,
    ))

    assert timed_out is True
    assert client.interrupted == ["task-timeout"]


def test_chat_json_is_compact_and_bounded_by_default(capsys):
    client = FakeTaskClient()
    with (
        patch("truffile.cli.chat._resolve_connected_device", _resolved),
        patch("truffile.cli.chat.TruffleClient", return_value=client),
    ):
        result = asyncio.run(_run_oneshot_chat(_chat_args(), FakeStorage()))

    assert result == 0
    payload = _json_stdout(capsys)
    assert payload["content"] == "0123456789"
    assert payload["content_bytes"] == 20
    assert payload["truncated"] is True
    assert payload["task_status"] == "ready"
    assert "thinking" not in payload
    assert "tool_calls" not in payload


def test_chat_rejects_non_positive_timeout_before_device_access(capsys):
    for timeout in (0, -1):
        with (
            patch("truffile.cli.chat._resolve_connected_device") as resolve,
            patch("truffile.cli.chat.TruffleClient") as client,
        ):
            result = asyncio.run(_run_oneshot_chat(
                _chat_args(timeout=timeout),
                FakeStorage(),
            ))

        assert result == 1
        resolve.assert_not_awaited()
        client.assert_not_called()
        payload = _json_stdout(capsys)
        assert payload["code"] == "invalid_args"
        assert payload["message"] == "--timeout must be greater than zero"


def test_chat_rejects_non_positive_output_limit_before_device_access(capsys):
    for max_output_bytes in (0, -1):
        with (
            patch("truffile.cli.chat._resolve_connected_device") as resolve,
            patch("truffile.cli.chat.TruffleClient") as client,
        ):
            result = asyncio.run(_run_oneshot_chat(
                _chat_args(max_output_bytes=max_output_bytes),
                FakeStorage(),
            ))

        assert result == 1
        resolve.assert_not_awaited()
        client.assert_not_called()
        payload = _json_stdout(capsys)
        assert payload["code"] == "invalid_args"
        assert payload["message"] == "--max-output-bytes must be greater than zero"


def test_chat_json_rejects_an_invalid_saved_session(capsys):
    client = RejectedTaskClient()
    with (
        patch("truffile.cli.chat._resolve_connected_device", _resolved),
        patch("truffile.cli.chat.TruffleClient", return_value=client),
    ):
        result = asyncio.run(_run_oneshot_chat(_chat_args(), FakeStorage()))

    assert result == 1
    payload = _json_stdout(capsys)
    assert payload["code"] == "authentication_failed"
    assert "truffile connect" in payload["next_action"]


def test_completed_task_follow_up_does_not_silently_create_a_new_task(capsys):
    client = CompletedTaskClient()
    with (
        patch("truffile.cli.chat._resolve_connected_device", _resolved),
        patch("truffile.cli.chat.TruffleClient", return_value=client),
    ):
        result = asyncio.run(_run_oneshot_chat(
            _chat_args(task_id="task-complete", prompt_words=["follow up"]),
            FakeStorage(),
        ))

    assert result == 1
    payload = _json_stdout(capsys)
    assert payload["code"] == "task_not_waiting"
    assert payload["task_id"] == "task-complete"
    assert "without --task-id" in payload["next_action"]
    assert client.new_prompts == []


def test_chat_full_json_opts_into_thinking_and_tools(capsys):
    client = FakeTaskClient()
    with (
        patch("truffile.cli.chat._resolve_connected_device", _resolved),
        patch("truffile.cli.chat.TruffleClient", return_value=client),
    ):
        result = asyncio.run(_run_oneshot_chat(
            _chat_args(full=True, max_output_bytes=100),
            FakeStorage(),
        ))

    assert result == 0
    payload = _json_stdout(capsys)
    assert payload["thinking"] == ["private summary"]
    assert payload["tool_calls"] == ["sensitive_tool"]
    assert payload["truncated"] is False


def test_task_infos_include_status_and_pending_state():
    response = GetTaskInfosResponse()
    pending = response.entries.add()
    pending.task_id = "task-pending"
    pending.info.task_title = "Needs input"
    pending.info.run_state = TaskInfo.TASK_RUN_STATE_READY
    pending.last_node.step.user_response.node_id = 7

    complete = response.entries.add()
    complete.task_id = "task-complete"
    complete.info.task_title = "Done"
    complete.info.run_state = TaskInfo.TASK_RUN_STATE_FATAL_ERROR
    complete.last_node.user_msg.content = "answer"

    class Stub:
        async def Task_GetTaskInfos(self, _request, metadata=None):
            return response

    client = TruffleClient("192.0.2.10:80", token="token")
    client.stub = Stub()

    tasks = asyncio.run(client.get_task_infos(max_before=2))

    assert tasks[0]["status"] == "ready"
    assert tasks[0]["pending_user_response"] is True
    assert tasks[0]["error"] is False
    assert tasks[1]["status"] == "fatal_error"
    assert tasks[1]["pending_user_response"] is False
    assert tasks[1]["error"] is True


def test_task_infos_are_newest_first_and_bounded():
    response = GetTaskInfosResponse()
    for task_id, hour in (("task-old", 8), ("task-new", 10), ("task-middle", 9)):
        entry = response.entries.add()
        entry.task_id = task_id
        entry.info.task_title = task_id
        entry.info.run_state = TaskInfo.TASK_RUN_STATE_READY
        entry.info.last_updated.FromDatetime(
            datetime(2026, 7, 15, hour, tzinfo=timezone.utc)
        )

    class Stub:
        async def Task_GetTaskInfos(self, _request, metadata=None):
            return response

    client = TruffleClient("192.0.2.10:80", token="token")
    client.stub = Stub()

    tasks = asyncio.run(client.get_task_infos(max_before=2))

    assert [task["task_id"] for task in tasks] == ["task-new", "task-middle"]
