from types import SimpleNamespace

import pytest

import truffile.cli as cli
from truffile.cli.chat import _is_oneshot_chat


def _invoke(monkeypatch, argv, *, isatty=True):
    calls = []
    storage = SimpleNamespace(
        state=SimpleNamespace(
            devices=[],
            last_used_device="truffle-test",
            client_user_id="user-test",
        )
    )

    monkeypatch.setattr("truffile.storage.StorageService", lambda: storage)
    monkeypatch.setattr(
        "truffile.cli.in_container.probe_in_container_device", lambda: None
    )
    monkeypatch.setattr("sys.stdin.isatty", lambda: isatty)

    async def fake_cmd_chat(args, received_storage):
        calls.append((args, received_storage))
        return 0

    monkeypatch.setattr("truffile.cli.chat.cmd_chat", fake_cmd_chat)
    monkeypatch.setattr("sys.argv", ["truffile", *argv])

    assert cli._main() == 0
    assert len(calls) == 1
    assert calls[0][1] is storage
    return calls[0][0]


def test_resume_without_id_keeps_interactive_picker(monkeypatch):
    args = _invoke(monkeypatch, ["chat", "--resume"])

    assert args.resume is True
    assert args.task_id is None
    assert _is_oneshot_chat(args) is False


def test_resume_id_reopens_interactively(monkeypatch):
    args = _invoke(monkeypatch, ["chat", "--resume", "task-123"])

    assert args.resume is True
    assert args.task_id == "task-123"
    assert _is_oneshot_chat(args) is False


def test_resume_id_with_prompt_continues_oneshot(monkeypatch):
    args = _invoke(
        monkeypatch,
        ["chat", "--resume", "task-123", "continue", "this", "task"],
    )

    assert args.task_id == "task-123"
    assert args.prompt_words == ["continue", "this", "task"]
    assert _is_oneshot_chat(args) is True


def test_resume_id_is_oneshot_without_tty(monkeypatch):
    args = _invoke(
        monkeypatch,
        ["chat", "--resume", "task-123"],
        isatty=False,
    )

    assert _is_oneshot_chat(args) is True


def test_resume_rejects_conflicting_task_id(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        ["truffile", "chat", "--resume", "task-123", "--task-id", "task-456"],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli._main()

    assert exc_info.value.code == 2
