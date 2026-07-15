import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from concurrent import futures

import grpc
import pytest

from truffle.os.app_queries_pb2 import GetAllAppsResponse
from truffle.os.system_info_pb2 import SystemGetIDResponse, SystemInfo
from truffle.os.task_actions_pb2 import (
    TaskActionResponse,
    TaskDeleteResponse,
)
from truffle.os.task_pb2 import Task, TaskStreamUpdate
from truffle.os.task_queries_pb2 import GetTaskInfosResponse
from truffle.os.truffleos_pb2_grpc import (
    TruffleOSServicer,
    add_TruffleOSServicer_to_server,
)


CLI_ENTRY = "from truffile.cli import main; raise SystemExit(main())"


class FakeTruffleOS(TruffleOSServicer):
    """Stateful protocol-level fake used to exercise real CLI subprocesses."""

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks = {}
        self._next_node_id = 1

    def _copy_task(self, task):
        copied = Task()
        copied.CopyFrom(task)
        return copied

    def _set_content(self, record, content):
        task = record["task"]
        del task.nodes[:]
        result = task.nodes.add()
        result.id = self._next_node_id
        self._next_node_id += 1
        result.step.results.content = f"ECHO:{content}"
        pending = task.nodes.add()
        pending.id = self._next_node_id
        self._next_node_id += 1
        pending.step.user_response.task_id = task.task_id
        pending.step.user_response.node_id = pending.id
        task.info.run_state = task.info.TASK_RUN_STATE_READY
        task.info.last_updated.GetCurrentTime()
        record["version"] += 1
        update = self._task_update(task)
        for updates in record["subscribers"]:
            updates.put(update)

    def _task_update(self, task):
        update = TaskStreamUpdate(task_id=task.task_id)
        update.info.CopyFrom(task.info)
        update.nodes.extend(task.nodes)
        return update

    def System_GetID(self, request, context):
        return SystemGetIDResponse(truffle_id="truffle-e2e", serial_number="test")

    def System_GetInfo(self, request, context):
        return SystemInfo()

    def Apps_GetAll(self, request, context):
        return GetAllAppsResponse()

    def Task_OpenTask(self, request, context):
        with self._lock:
            if request.HasField("new_task"):
                task_id = str(uuid.uuid4())
                task = Task(task_id=task_id)
                task.info.task_title = "E2E task"
                task.info.created.GetCurrentTime()
                task.info.last_updated.CopyFrom(task.info.created)
                record = {
                    "task": task,
                    "version": 0,
                    "subscribers": [],
                }
                self._tasks[task_id] = record
                self._set_content(record, request.new_task.user_message.content)
                initial_version = -1
            else:
                task_id = request.existing_task.task_id
                record = self._tasks.get(task_id)
                if record is None:
                    context.abort(grpc.StatusCode.NOT_FOUND, "task not found")
                initial_version = record["version"]
            updates = queue.Queue()
            record["subscribers"].append(updates)

        # A one-shot resume responds immediately after opening the stream,
        # whereas an interactive resume reads the snapshot first. This short
        # window lets the fake reproduce both firmware behaviors.
        if initial_version >= 0:
            time.sleep(0.05)
        with self._lock:
            yield self._task_update(record["task"])

        try:
            while context.is_active():
                try:
                    yield updates.get(timeout=0.1)
                except queue.Empty:
                    continue
        finally:
            with self._lock:
                if updates in record["subscribers"]:
                    record["subscribers"].remove(updates)

    def Task_RespondToTask(self, request, context):
        with self._lock:
            record = self._tasks.get(request.task_id)
            if record is None:
                context.abort(grpc.StatusCode.NOT_FOUND, "task not found")
            self._set_content(record, request.message.content)
        return TaskActionResponse()

    def Task_GetOneTask(self, request, context):
        with self._lock:
            record = self._tasks.get(request.task_id)
            if record is None:
                context.abort(grpc.StatusCode.NOT_FOUND, "task not found")
            return self._copy_task(record["task"])

    def Task_GetTaskInfos(self, request, context):
        response = GetTaskInfosResponse()
        with self._lock:
            records = sorted(
                self._tasks.values(),
                key=lambda record: record["task"].info.last_updated.ToNanoseconds(),
                reverse=True,
            )
            for record in records[: request.max_before or 20]:
                entry = response.entries.add()
                entry.task_id = record["task"].task_id
                entry.info.CopyFrom(record["task"].info)
            response.total_num_tasks = len(records)
        return response

    def Task_Delete(self, request, context):
        with self._lock:
            if self._tasks.pop(request.task_id, None) is None:
                context.abort(grpc.StatusCode.NOT_FOUND, "task not found")
        return TaskDeleteResponse()

    def Task_InterruptTask(self, request, context):
        return TaskActionResponse()


@pytest.fixture
def fake_truffle(tmp_path):
    service = FakeTruffleOS()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    add_TruffleOSServicer_to_server(service, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    env = os.environ.copy()
    env.update(
        {
            "APP_ID": "e2e-app",
            "APP_SESSION_TOKEN": "e2e-token",
            "GRPC_ADDRESS": f"127.0.0.1:{port}",
            "HOME": str(tmp_path),
            "XDG_DATA_HOME": str(tmp_path / "data"),
        }
    )
    try:
        yield env
    finally:
        server.stop(grace=0).wait()


def run_cli(env, *args):
    return subprocess.run(
        [sys.executable, "-c", CLI_ENTRY, *args],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=15,
    )


def run_tty_cli_until(env, expected: bytes, *args):
    """Run the real interactive CLI in a PTY, then exit with Ctrl-D."""
    import pty
    import select

    master_fd, slave_fd = pty.openpty()
    process = subprocess.Popen(
        [sys.executable, "-c", CLI_ENTRY, *args],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        close_fds=True,
    )
    os.close(slave_fd)
    output = bytearray()
    alive_before_eof = False
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline and process.poll() is None:
            readable, _, _ = select.select([master_fd], [], [], 0.25)
            if not readable:
                continue
            try:
                output.extend(os.read(master_fd, 4096))
            except OSError:
                break
            if expected in output:
                time.sleep(0.25)
                alive_before_eof = process.poll() is None
                if alive_before_eof:
                    os.write(master_fd, b"\x04")
                break
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        os.close(master_fd)
    return process.returncode, bytes(output), alive_before_eof


def test_cli_run_resume_last_and_task_lifecycle_end_to_end(fake_truffle):
    created = run_cli(fake_truffle, "run", "alpha", "--json", "--quiet")
    assert created.returncode == 0, created.stderr
    created_payload = json.loads(created.stdout)
    task_id = created_payload["task_id"]
    assert created_payload["operation"] == "run"
    assert created_payload["content"] == "ECHO:alpha"

    exact = run_cli(
        fake_truffle,
        "run",
        "--resume",
        task_id,
        "beta",
        "--json",
        "--quiet",
    )
    assert exact.returncode == 0, exact.stderr
    exact_payload = json.loads(exact.stdout)
    assert exact_payload["task_id"] == task_id
    assert exact_payload["operation"] == "resume"
    assert exact_payload["content"] == "ECHO:beta"

    latest = run_cli(fake_truffle, "run", "--last", "gamma", "--json", "--quiet")
    assert latest.returncode == 0, latest.stderr
    latest_payload = json.loads(latest.stdout)
    assert latest_payload["task_id"] == task_id
    assert latest_payload["content"] == "ECHO:gamma"

    listed = run_cli(fake_truffle, "task", "list", "--json")
    assert listed.returncode == 0, listed.stderr
    assert json.loads(listed.stdout)["tasks"][0]["task_id"] == task_id

    deleted = run_cli(fake_truffle, "task", "delete", task_id, "--yes", "--json")
    assert deleted.returncode == 0, deleted.stderr
    assert json.loads(deleted.stdout)["status"] == "deleted"

    missing = run_cli(fake_truffle, "run", "--resume", task_id, "no fork", "--json", "--quiet")
    assert missing.returncode == 4
    assert json.loads(missing.stdout)["error"]["code"] == "not_found"


def test_cli_ephemeral_resume_is_rejected_without_rpc(fake_truffle):
    result = run_cli(
        fake_truffle,
        "run",
        "--resume",
        "task-1",
        "--ephemeral",
        "unsafe",
        "--json",
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "usage_error"


@pytest.mark.skipif(os.name == "nt", reason="pseudo-terminal smoke test is POSIX-only")
def test_interactive_resume_and_bare_prompt_end_to_end(fake_truffle):
    created = run_cli(fake_truffle, "run", "seed", "--json", "--quiet")
    assert created.returncode == 0, created.stderr
    task_id = json.loads(created.stdout)["task_id"]

    returncode, output, alive_before_eof = run_tty_cli_until(
        fake_truffle,
        b"ECHO:interactive-resume",
        "resume",
        "--last",
        "interactive-resume",
    )
    assert returncode == 0, output.decode(errors="replace")
    assert b"ECHO:interactive-resume" in output
    assert alive_before_eof, "interactive resume exited before Ctrl-D"

    resumed = run_cli(fake_truffle, "task", "show", task_id, "--json", "--quiet")
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)["content"] == "ECHO:interactive-resume"

    returncode, output, alive_before_eof = run_tty_cli_until(
        fake_truffle,
        b"ECHO:bare-interactive",
        "bare-interactive",
    )
    assert returncode == 0, output.decode(errors="replace")
    assert b"ECHO:bare-interactive" in output
    assert alive_before_eof, "bare interactive session exited before Ctrl-D"

    latest = run_cli(fake_truffle, "task", "list", "--limit", "1", "--json")
    assert latest.returncode == 0, latest.stderr
    latest_id = json.loads(latest.stdout)["tasks"][0]["task_id"]
    assert latest_id != task_id
    bare = run_cli(fake_truffle, "task", "show", latest_id, "--json", "--quiet")
    assert json.loads(bare.stdout)["content"] == "ECHO:bare-interactive"
