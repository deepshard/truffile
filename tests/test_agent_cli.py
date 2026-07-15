import asyncio
import subprocess
import sys
from types import SimpleNamespace

import truffile.cli as cli
from truffile.cli import agent
from truffile.cli.chat import TaskState, _resolve_app_refs, _task_status
from truffile.cli.exit_codes import USAGE
from truffile.transport.client import _sort_task_infos


CLI_ENTRY = "from truffile.cli import main; raise SystemExit(main())"


def run_cli_help(*args):
    return subprocess.run(
        [sys.executable, "-c", CLI_ENTRY, *args],
        capture_output=True,
        check=False,
        text=True,
    )


def test_help_promotes_direct_workflow_and_hides_legacy_namespaces():
    result = run_cli_help("--help")

    assert result.returncode == 0
    assert "run         run a task non-interactively" in result.stdout
    assert "resume      resume an interactive task" in result.stdout
    assert "shell       " not in result.stdout
    assert "agent       " not in result.stdout
    assert "chat        " not in result.stdout


def test_direct_workflow_help_exposes_automation_flags():
    run_help = run_cli_help("run", "--help")
    resume_help = run_cli_help("resume", "--help")
    shell_help = run_cli_help("shell", "--help")

    assert run_help.returncode == resume_help.returncode == shell_help.returncode == 0
    assert "--ephemeral" in run_help.stdout
    assert "--json" in run_help.stdout
    assert "--resume TASK_ID" in run_help.stdout
    assert "--last" in run_help.stdout
    assert "--last" in resume_help.stdout
    assert "TASK_ID" in resume_help.stdout
    assert "--json" not in resume_help.stdout
    assert "TASK_ID" in shell_help.stdout


def test_hidden_agent_namespace_remains_parseable_for_compatibility():
    result = run_cli_help("agent", "run", "--help")

    assert result.returncode == 0
    assert "usage: truffile agent run" in result.stdout


def test_bare_prompt_routes_to_hidden_interactive_entrypoint():
    assert cli._normalize_cli_argv(["fix", "the", "bug"]) == [
        "shell",
        "--new",
        "--",
        "fix",
        "the",
        "bug",
    ]
    assert cli._normalize_cli_argv(["--", "--literal-prompt"]) == [
        "shell",
        "--new",
        "--",
        "--literal-prompt",
    ]
    assert cli._normalize_cli_argv(["run", "fix"]) == ["run", "fix"]


def test_direct_commands_route_to_the_persistent_task_runtime(monkeypatch, capsys):
    routed = []

    async def fake_agent(args, storage):
        routed.append((args.command, args.agent_command, list(getattr(args, "prompt_words", []))))
        return 0

    fake_storage = SimpleNamespace(
        state=SimpleNamespace(last_used_device="truffle-test", devices=[]),
    )
    monkeypatch.setattr("truffile.storage.StorageService", lambda: fake_storage)
    monkeypatch.setattr("truffile.cli.in_container.probe_in_container_device", lambda: None)
    monkeypatch.setattr(agent, "cmd_agent", fake_agent)

    monkeypatch.setattr(sys, "argv", ["truffile", "run", "start", "here"])
    assert cli._main() == 0
    monkeypatch.setattr(sys, "argv", ["truffile", "resume", "task-1", "continue"])
    assert cli._main() == 0
    monkeypatch.setattr(sys, "argv", ["truffile", "shell", "task-1"])
    assert cli._main() == 0
    monkeypatch.setattr(sys, "argv", ["truffile", "agent", "run", "legacy"])
    assert cli._main() == 0

    assert routed == [
        ("run", "run", ["start", "here"]),
        ("resume", "resume", ["continue"]),
        ("shell", "shell", []),
        ("agent", "run", ["legacy"]),
    ]
    assert "'truffile agent' is deprecated" in capsys.readouterr().err


def test_sort_task_infos_is_newest_first_and_deterministic():
    tasks = [
        {"task_id": "older", "created": "2026-01-01", "updated": "2026-01-02"},
        {"task_id": "newer", "created": "2026-01-01", "updated": "2026-01-03"},
        {"task_id": "middle", "created": "2026-01-01", "updated": "2026-01-02T12:00"},
    ]

    assert [task["task_id"] for task in _sort_task_infos(tasks)] == [
        "newer",
        "middle",
        "older",
    ]


def test_ambiguous_app_substring_is_rejected():
    apps = [
        {"uuid": "one", "name": "Alpha Search"},
        {"uuid": "two", "name": "Beta Search"},
    ]

    matched, unmatched = _resolve_app_refs(["search"], apps)

    assert matched == []
    assert unmatched == ["search"]


def test_task_status_prefers_pending_user_response():
    state = TaskState(
        run_state="TASK_RUN_STATE_READY",
        pending_node_id=7,
    )

    assert _task_status(state) == "waiting_for_user"


def test_agent_continue_is_exact_resume_last_alias(monkeypatch):
    captured = {}

    async def fake_chat(args, storage):
        captured.update(vars(args))
        return 0

    monkeypatch.setattr(agent, "cmd_chat", fake_chat)
    args = SimpleNamespace(
        agent_command="continue",
        prompt_words=["follow", "up"],
        device=None,
        json=False,
    )

    assert asyncio.run(agent.cmd_agent(args, object())) == 0
    assert captured["resume_last"] is True
    assert captured["task_id"] is None
    assert captured["force_oneshot"] is True


def test_agent_resume_last_reclassifies_first_positional_as_prompt(monkeypatch):
    captured = {}

    async def fake_chat(args, storage):
        captured.update(vars(args))
        return 0

    monkeypatch.setattr(agent, "cmd_chat", fake_chat)
    args = SimpleNamespace(
        agent_command="resume",
        last=True,
        task_id="first",
        prompt_words=["second"],
        device=None,
        json=False,
    )

    assert asyncio.run(agent.cmd_agent(args, object())) == 0
    assert captured["resume_last"] is True
    assert captured["task_id"] is None
    assert captured["prompt_words"] == ["first", "second"]


def test_direct_run_can_resume_exact_context_noninteractively(monkeypatch):
    captured = {}

    async def fake_chat(args, storage):
        captured.update(vars(args))
        return 0

    monkeypatch.setattr(agent, "cmd_chat", fake_chat)
    args = SimpleNamespace(
        agent_command="run",
        resume_task_id="task-1",
        last=False,
        prompt_words=["follow-up"],
        ephemeral=False,
        device=None,
        json=True,
    )

    assert asyncio.run(agent.cmd_agent(args, object())) == 0
    assert captured["task_id"] == "task-1"
    assert captured["resume_last"] is False
    assert captured["force_oneshot"] is True


def test_ephemeral_resume_is_rejected_before_execution(monkeypatch):
    called = False

    async def fake_chat(args, storage):
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(agent, "cmd_chat", fake_chat)
    args = SimpleNamespace(
        agent_command="run",
        resume_task_id="task-1",
        last=False,
        prompt_words=["follow-up"],
        ephemeral=True,
        device=None,
        json=True,
    )

    assert asyncio.run(agent.cmd_agent(args, object())) == USAGE
    assert called is False


def test_direct_resume_is_interactive_and_last_reclassifies_prompt(monkeypatch):
    captured = {}

    async def fake_chat(args, storage):
        captured.update(vars(args))
        return 0

    monkeypatch.setattr(agent, "cmd_chat", fake_chat)
    args = SimpleNamespace(
        agent_command="resume",
        interactive_resume=True,
        last=True,
        task_id="first",
        prompt_words=["second"],
        device=None,
    )

    assert asyncio.run(agent.cmd_agent(args, object())) == 0
    assert captured["resume_last"] is True
    assert captured["task_id"] is None
    assert captured["prompt_words"] == ["first", "second"]
    assert captured["force_oneshot"] is False
    assert captured["force_interactive"] is True


def test_bare_prompt_entrypoint_becomes_new_interactive_task(monkeypatch):
    captured = {}

    async def fake_chat(args, storage):
        captured.update(vars(args))
        return 0

    monkeypatch.setattr(agent, "cmd_chat", fake_chat)
    args = SimpleNamespace(
        agent_command="shell",
        new=True,
        resume=False,
        task_id="fix",
        prompt_words=["the", "bug"],
        device=None,
    )

    assert asyncio.run(agent.cmd_agent(args, object())) == 0
    assert captured["task_id"] is None
    assert captured["prompt_words"] == ["fix", "the", "bug"]
    assert captured["force_oneshot"] is False
    assert captured["force_interactive"] is True
