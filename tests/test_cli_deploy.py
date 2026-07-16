import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from truffile.cli.deploy import _non_interactive_blockers, _plan_json, cmd_deploy


class _Storage:
    def get_token(self, _device: str) -> str:
        return "token"

    def app_id_for_device(self, _device: str) -> None:
        return None


class _Client:
    def __init__(self) -> None:
        self.app_uuid = None
        self.last_app_uuid = "build-session"

    async def close(self) -> None:
        pass


def _deploy_args(app_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        path=str(app_dir),
        interactive=False,
        dry_run=False,
        json=True,
        non_interactive=True,
        replace=False,
    )


def _deploy_plan() -> dict:
    return {
        "name": "Smoke",
        "bundle_id": "org.truffle.smoke",
        "finish_label": "foreground",
        "ordered_steps": [],
    }


@pytest.mark.parametrize("failure", [False, True])
def test_real_deploy_json_suppresses_progress_on_stdout_and_stderr(
    tmp_path: Path,
    capsys,
    failure: bool,
) -> None:
    (tmp_path / "icon.png").write_bytes(b"icon")
    config = {"metadata": {"icon_file": "icon.png"}}
    client = _Client()

    async def resolved(_storage, *, quiet=False):
        return "truffle-1234", "192.0.2.10"

    async def deploy(**_kwargs):
        print("builder progress")
        print("builder warning", file=sys.stderr)
        if failure:
            raise RuntimeError("builder failed")
        return 0

    with (
        patch("truffile.cli.deploy.validate_app_dir", return_value=(True, config, "foreground", [], [])),
        patch("truffile.cli.deploy.build_deploy_plan", return_value=_deploy_plan()),
        patch("truffile.cli.deploy._resolve_connected_device", resolved),
        patch("truffile.cli.deploy.TruffleClient", return_value=client),
        patch("truffile.cli.deploy.deploy_with_builder", deploy),
    ):
        result = asyncio.run(cmd_deploy(_deploy_args(tmp_path), _Storage()))

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    if failure:
        assert result == 1
        assert payload["code"] == "deploy_failed"
        assert payload["message"] == "builder failed"
    else:
        assert result == 0
        assert payload["status"] == "ok"
        assert payload["build_session"] == "build-session"


def test_non_interactive_blockers_allow_welcome_but_block_text_and_oauth():
    plan = {
        "ordered_steps": [
            {"type": "welcome", "name": "Hello"},
            {"type": "files", "name": "Copy"},
            {"type": "text", "name": "API key"},
            {"type": "oauth", "name": "Sign in"},
        ]
    }

    assert _non_interactive_blockers(plan) == [
        {"type": "text", "name": "API key"},
        {"type": "oauth", "name": "Sign in"},
    ]


def test_plan_json_is_compact_for_agents():
    plan = {
        "name": "Smoke",
        "bundle_id": "org.truffle.smoke",
        "finish_label": "foreground",
        "files_to_upload": [
            {"source": "./app.py", "destination": "./app.py"},
        ],
        "bash_commands": [("Install", "pip install -r requirements.txt")],
        "ordered_steps": [
            {"type": "welcome", "name": "Welcome"},
            {"type": "text", "name": "API key"},
            {"type": "oauth", "name": "Sign in"},
        ],
    }

    assert _plan_json(plan, Path("/tmp/smoke")) == {
        "name": "Smoke",
        "bundle_id": "org.truffle.smoke",
        "mode": "foreground",
        "app_dir": "/tmp/smoke",
        "files": [{"source": "./app.py", "destination": "./app.py"}],
        "bash_steps": ["Install"],
        "steps": [
            {"type": "welcome", "name": "Welcome", "requires_input": False},
            {"type": "text", "name": "API key", "requires_input": True},
            {"type": "oauth", "name": "Sign in", "requires_input": True},
        ],
        "input_requirements": [
            {"type": "text", "name": "API key"},
            {"type": "oauth", "name": "Sign in"},
        ],
    }


def test_non_interactive_dry_run_reports_input_boundaries_without_blocking(
    tmp_path: Path,
    capsys,
) -> None:
    (tmp_path / "icon.png").write_bytes(b"icon")
    config = {"metadata": {"icon_file": "icon.png"}}
    plan = {
        "name": "Auth app",
        "bundle_id": "org.truffle.auth-app",
        "finish_label": "foreground",
        "ordered_steps": [
            {"type": "welcome", "name": "Introduction"},
            {"type": "oauth", "name": "Connect account"},
            {"type": "text", "name": "API key"},
        ],
        "files_to_upload": [],
        "bash_commands": [],
    }
    args = _deploy_args(tmp_path)
    args.dry_run = True

    with (
        patch("truffile.cli.deploy.validate_app_dir", return_value=(True, config, "foreground", [], [])),
        patch("truffile.cli.deploy.build_deploy_plan", return_value=plan),
        patch("truffile.cli.deploy._resolve_connected_device") as resolve,
    ):
        result = asyncio.run(cmd_deploy(args, _Storage()))

    assert result == 0
    resolve.assert_not_awaited()
    payload = json.loads(capsys.readouterr().out)
    assert payload["app"]["steps"] == [
        {"type": "welcome", "name": "Introduction", "requires_input": False},
        {"type": "oauth", "name": "Connect account", "requires_input": True},
        {"type": "text", "name": "API key", "requires_input": True},
    ]
    assert payload["app"]["input_requirements"] == [
        {"type": "oauth", "name": "Connect account"},
        {"type": "text", "name": "API key"},
    ]
