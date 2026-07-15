import asyncio
import json
from types import SimpleNamespace

from truffle.os.task_pb2 import Task
from truffle.os.task_pb2 import TaskStreamUpdate
from truffile.cli import task as task_cli
from truffile.cli.exit_codes import USAGE
from truffile.cli.task import _dispatch_task, _task_events


def make_task():
    task = Task(task_id="task-1")
    task.info.run_state = task.info.TASK_RUN_STATE_READY
    user = task.nodes.add()
    user.id = 1
    user.user_msg.content = "hello"
    result = task.nodes.add()
    result.id = 2
    result.step.results.content = "world"
    pending = task.nodes.add()
    pending.id = 3
    pending.step.user_response.task_id = "task-1"
    pending.step.user_response.node_id = 3
    return task


class FakeClient:
    def __init__(self):
        self.task = make_task()
        self.deleted = []

    async def get_task(self, task_id, *, with_nodes=True):
        return self.task

    async def delete_task(self, task_id):
        self.deleted.append(task_id)


def test_task_events_preserve_user_result_and_waiting_boundary():
    events = _task_events(make_task())

    assert [event["type"] for event in events] == [
        "user",
        "result",
        "waiting_for_user",
    ]
    assert events[0]["content"] == "hello"
    assert events[1]["content"] == "world"


def test_task_delete_requires_yes_for_json(monkeypatch, capsys):
    client = FakeClient()
    args = SimpleNamespace(
        task_command="delete",
        task_id="task-1",
        yes=False,
        json=True,
        quiet=True,
    )

    result = asyncio.run(_dispatch_task(args, client, "truffle-1234"))
    payload = json.loads(capsys.readouterr().out)

    assert result == USAGE
    assert payload["error"]["code"] == "usage_error"
    assert client.deleted == []


def test_task_delete_yes_is_noninteractive(capsys):
    client = FakeClient()
    args = SimpleNamespace(
        task_command="delete",
        task_id="task-1",
        yes=True,
        json=True,
        quiet=True,
    )

    result = asyncio.run(_dispatch_task(args, client, "truffle-1234"))
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["status"] == "deleted"
    assert client.deleted == ["task-1"]


def test_task_wait_timeout_does_not_interrupt_task(monkeypatch, capsys):
    task = Task(task_id="running")
    task.info.run_state = task.info.TASK_RUN_STATE_CREATING_NEW

    class SlowClient:
        def __init__(self):
            self.interrupted = []

        async def connect(self):
            return None

        async def check_auth(self):
            return True

        async def close(self):
            return None

        async def get_task(self, task_id, *, with_nodes=True):
            return task

        def open_existing_task_stream(self, task_id):
            async def stream():
                update = TaskStreamUpdate(task_id=task_id)
                update.info.run_state = update.info.TASK_RUN_STATE_CREATING_NEW
                yield update
                await asyncio.sleep(60)

            return stream()

        async def interrupt_task(self, task_id):
            self.interrupted.append(task_id)

    client = SlowClient()

    async def fake_resolve(storage, requested_device=None, *, emit_errors=True):
        return "truffle-1234", "127.0.0.1"

    monkeypatch.setattr(task_cli, "_resolve_connected_device", fake_resolve)
    monkeypatch.setattr(task_cli, "TruffleClient", lambda *args, **kwargs: client)
    storage = SimpleNamespace(
        get_token=lambda device: "token",
        app_id_for_device=lambda device: None,
    )
    args = SimpleNamespace(
        task_command="wait",
        task_id="running",
        timeout=0.01,
        device="truffle-1234",
        json=True,
        quiet=True,
    )

    result = asyncio.run(task_cli.cmd_task(args, storage))
    payload = json.loads(capsys.readouterr().out)

    assert result == 124
    assert payload["error"]["code"] == "timeout"
    assert client.interrupted == []
