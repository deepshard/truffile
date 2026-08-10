import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from truffile.cli import _main
from truffile.cli import chat
from truffile.convo_chat import ConvoTurnResult, ThreadSelectionError


class Tty:
    def isatty(self):
        return True


def args(**overrides):
    values = {
        "prompt_words": [],
        "prompt_file": None,
        "stdin": False,
        "main": False,
        "thread": None,
        "thread_id": None,
        "resume_last": False,
        "new": False,
        "rename": None,
        "history": False,
        "interrupt": False,
        "hide": None,
        "restore": None,
        "include_hidden": False,
        "list_apps": False,
        "list_threads": None,
        "app": None,
        "json": False,
        "show_thinking": False,
        "quiet": True,
        "timeout": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_convo_is_public_command_and_chat_is_not_advertised(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["truffile", "--help"])
    with pytest.raises(SystemExit) as exc:
        _main()
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert "convo" in output
    assert "agent chat" not in output
    assert "convo-reset" not in output


def test_convo_help_documents_agent_drivable_flags(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["truffile", "convo", "--help"])
    with pytest.raises(SystemExit):
        _main()
    output = capsys.readouterr().out
    for flag in ("--main", "--thread", "--new", "--rename", "--history", "--interrupt", "--json", "--timeout"):
        assert flag in output


def test_convo_reset_spelling_still_parses(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["truffile", "convo", "reset", "--help"])
    with pytest.raises(SystemExit) as exc:
        _main()
    assert exc.value.code == 0
    assert "truffile convo" in capsys.readouterr().out


def test_interactive_default_is_draft_but_main_alone_stays_interactive(monkeypatch):
    monkeypatch.setattr(sys, "stdin", Tty())
    assert chat._is_oneshot_chat(args()) is False
    assert chat._is_oneshot_chat(args(main=True)) is False
    assert chat._is_oneshot_chat(args(prompt_words=["hello"])) is True
    assert chat._is_oneshot_chat(args(main=True, prompt_words=["hello"])) is True


def test_json_result_has_canonical_and_compatibility_fields():
    payload = chat._result_payload(
        ConvoTurnResult(thread_id=42, user_node_id=9, title="Named", content="ok"),
        "truffle-6272",
    )
    assert payload["thread_id"] == "42"
    assert payload["task_id"] == "42"
    assert payload["backend"] == "convo"
    assert payload["attached_apps"] is None


def test_legacy_task_uuid_fails_before_selection():
    class Session:
        pass

    with pytest.raises(ThreadSelectionError, match="legacy Task chats"):
        asyncio.run(
            chat._select_target(
                Session(), args(thread_id="0c83cc07-4ee5-410f-8c0a-be8152644f24")
            )
        )


class FakeClient:
    async def close(self):
        return None


class FakeSession:
    def __init__(self, result=None):
        self.selected_thread_id = None
        self.result = result or ConvoTurnResult(
            thread_id=42, user_node_id=10, title="Untitled chat", content="answer"
        )
        self.renamed = None
        self.sent = []

    def new_thread(self):
        self.selected_thread_id = None

    async def send(self, message, timeout=None):
        self.sent.append((message, timeout, self.selected_thread_id))
        self.selected_thread_id = self.result.thread_id
        return self.result

    async def rename_selected(self, name):
        self.renamed = name

    async def close(self):
        return None


def test_one_shot_new_named_thread_is_machine_readable(monkeypatch, capsys):
    session = FakeSession()

    async def connect(_storage, quiet):
        return "truffle-6272", FakeClient()

    async def start(_client, _storage, _device):
        return session, "user-1"

    monkeypatch.setattr(chat, "_connect_client", connect)
    monkeypatch.setattr(chat, "_start_session", start)
    rc = asyncio.run(
        chat._run_oneshot_chat(
            args(
                prompt_words=["hello"],
                new=True,
                rename="QA debug",
                json=True,
                timeout=30,
            ),
            object(),
        )
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["thread_id"] == "42"
    assert payload["title"] == "QA debug"
    assert session.sent == [("hello", 30, None)]
    assert session.renamed == "QA debug"


def test_timeout_result_exits_124(monkeypatch, capsys):
    result = ConvoTurnResult(
        thread_id=42,
        user_node_id=10,
        title="Slow",
        content="partial",
        status="timeout",
        error="timed out",
        timed_out=True,
    )
    session = FakeSession(result)

    async def connect(_storage, quiet):
        return "truffle-6272", FakeClient()

    async def start(_client, _storage, _device):
        return session, "user-1"

    monkeypatch.setattr(chat, "_connect_client", connect)
    monkeypatch.setattr(chat, "_start_session", start)
    rc = asyncio.run(
        chat._run_oneshot_chat(
            args(prompt_words=["slow"], json=True, timeout=0.01), object()
        )
    )
    assert rc == 124
    assert json.loads(capsys.readouterr().out)["timed_out"] is True


def test_app_restriction_is_rejected_before_connection(monkeypatch, capsys):
    async def should_not_connect(*_args, **_kwargs):
        raise AssertionError("connection should not be attempted")

    monkeypatch.setattr(chat, "_connect_client", should_not_connect)
    rc = asyncio.run(
        chat._run_oneshot_chat(
            args(prompt_words=["hello"], app=["slack"], json=True), object()
        )
    )
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert "not supported" in payload["error"]
