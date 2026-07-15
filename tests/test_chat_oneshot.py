import asyncio
import json
from types import SimpleNamespace

from truffle.os.task_pb2 import Task, TaskStreamUpdate
from truffile.cli import chat
from truffile.cli.exit_codes import NOT_FOUND, TIMEOUT


class FakeStorage:
    def get_token(self, device):
        return "token"

    def app_id_for_device(self, device):
        return None


class AsyncStream:
    def __init__(self, updates):
        self._updates = iter(updates)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._updates)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeClient:
    def __init__(self, task=None, stream=None, task_infos=None):
        self.task = task or Task()
        self.stream = stream
        self.task_infos = task_infos or []
        self.new_task_calls = 0
        self.responses = []
        self.interrupted = []
        self.deleted = []

    async def connect(self):
        return None

    async def check_auth(self):
        return True

    async def close(self):
        return None

    async def get_task(self, task_id, *, with_nodes=True):
        return self.task

    async def get_task_infos(self, *, max_before=20):
        return self.task_infos[:max_before]

    def open_existing_task_stream(self, task_id):
        return self.stream

    def open_task_stream(self, prompt, *, app_uuids=None):
        self.new_task_calls += 1
        return self.stream

    async def respond_to_task(self, task_id, node_id, message):
        self.responses.append((task_id, node_id, message))

    async def set_task_apps(self, task_id, app_uuids):
        return None

    async def interrupt_task(self, task_id):
        self.interrupted.append(task_id)

    async def delete_task(self, task_id):
        self.deleted.append(task_id)


def make_args(**overrides):
    values = {
        "prompt_words": [],
        "prompt_file": None,
        "stdin": False,
        "task_id": None,
        "resume_last": False,
        "app": None,
        "list_apps": False,
        "list_tasks": None,
        "json": True,
        "show_thinking": False,
        "quiet": True,
        "timeout": None,
        "device": "truffle-1234",
        "ephemeral": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_task(task_id="task-1", pending_node_id=7):
    task = Task(task_id=task_id)
    task.info.run_state = task.info.TASK_RUN_STATE_READY
    task.info.task_title = "Remember marker"
    result = task.nodes.add()
    result.id = 1
    result.step.results.content = "FIRST"
    pending = task.nodes.add()
    pending.id = 2
    pending.step.user_response.task_id = task_id
    pending.step.user_response.node_id = pending_node_id
    return task


def make_update(task_id, *, content=None, pending_node_id=None):
    update = TaskStreamUpdate(task_id=task_id)
    update.info.run_state = update.info.TASK_RUN_STATE_READY
    if content is not None:
        node = update.nodes.add()
        node.id = 3
        node.step.results.content = content
    if pending_node_id is not None:
        node = update.nodes.add()
        node.id = 4
        node.step.user_response.task_id = task_id
        node.step.user_response.node_id = pending_node_id
    return update


def install_fake_runtime(monkeypatch, client):
    async def fake_resolve(storage, requested_device=None, *, emit_errors=True):
        return "truffle-1234", "127.0.0.1"

    monkeypatch.setattr(chat, "_resolve_connected_device", fake_resolve)
    monkeypatch.setattr(chat, "TruffleClient", lambda *args, **kwargs: client)


def test_missing_resume_target_never_opens_new_task(monkeypatch, capsys):
    client = FakeClient(task=Task())
    install_fake_runtime(monkeypatch, client)
    args = make_args(
        task_id="missing",
        prompt_words=["must", "not", "fork"],
    )

    result = asyncio.run(chat._run_oneshot_chat(args, FakeStorage()))
    payload = json.loads(capsys.readouterr().out)

    assert result == NOT_FOUND
    assert payload["error"]["code"] == "not_found"
    assert client.new_task_calls == 0
    assert client.responses == []


def test_exact_resume_keeps_task_id_and_uses_pending_node(monkeypatch, capsys):
    task = make_task()
    initial = make_update("task-1", pending_node_id=7)
    completed = make_update("task-1", content="SECOND", pending_node_id=9)
    client = FakeClient(task=task, stream=AsyncStream([initial, completed]))
    install_fake_runtime(monkeypatch, client)
    args = make_args(task_id="task-1", prompt_words=["follow-up"])

    result = asyncio.run(chat._run_oneshot_chat(args, FakeStorage()))
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["task_id"] == "task-1"
    assert payload["operation"] == "resume"
    assert payload["content"] == "SECOND"
    assert payload["status"] == "waiting_for_user"
    assert client.responses == [("task-1", 7, "follow-up")]
    assert client.new_task_calls == 0


def test_resume_last_selects_newest_task_without_forking(monkeypatch, capsys):
    task = make_task(task_id="latest")
    initial = make_update("latest", pending_node_id=7)
    completed = make_update("latest", content="CONTINUED", pending_node_id=9)
    client = FakeClient(
        task=task,
        stream=AsyncStream([initial, completed]),
        task_infos=[{"task_id": "latest"}],
    )
    install_fake_runtime(monkeypatch, client)
    args = make_args(resume_last=True, prompt_words=["follow-up"])

    result = asyncio.run(chat._run_oneshot_chat(args, FakeStorage()))
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["task_id"] == "latest"
    assert payload["operation"] == "resume"
    assert payload["content"] == "CONTINUED"
    assert client.responses == [("latest", 7, "follow-up")]
    assert client.new_task_calls == 0


def test_resume_last_missing_target_never_opens_new_task(monkeypatch, capsys):
    client = FakeClient(task_infos=[])
    install_fake_runtime(monkeypatch, client)
    args = make_args(resume_last=True, prompt_words=["must", "not", "fork"])

    result = asyncio.run(chat._run_oneshot_chat(args, FakeStorage()))
    payload = json.loads(capsys.readouterr().out)

    assert result == NOT_FOUND
    assert payload["error"]["code"] == "not_found"
    assert client.new_task_calls == 0


def test_timeout_interrupts_new_task_and_returns_124(monkeypatch, capsys):
    client = FakeClient()

    async def slow_stream():
        yield make_update("slow-task")
        await asyncio.sleep(60)

    client.stream = slow_stream()
    install_fake_runtime(monkeypatch, client)
    args = make_args(prompt_words=["slow"], timeout=0.01)

    result = asyncio.run(chat._run_oneshot_chat(args, FakeStorage()))
    payload = json.loads(capsys.readouterr().out)

    assert result == TIMEOUT
    assert payload["error"]["code"] == "timeout"
    assert payload["task_id"] == "slow-task"
    assert client.interrupted == ["slow-task"]


def test_ephemeral_run_deletes_completed_task(monkeypatch, capsys):
    completed = make_update("temporary", content="DONE", pending_node_id=2)
    client = FakeClient(stream=AsyncStream([completed]))
    install_fake_runtime(monkeypatch, client)
    args = make_args(prompt_words=["temporary"], ephemeral=True)

    result = asyncio.run(chat._run_oneshot_chat(args, FakeStorage()))
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["ephemeral"] is True
    assert payload["content"] == "DONE"
    assert client.deleted == ["temporary"]
