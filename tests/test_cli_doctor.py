import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from truffile import __version__
from truffile.cli import _main
from truffile.cli.doctor import cmd_doctor
from truffile.storage import StoredState


class FakeStorage:
    def __init__(self, *, device: str | None = "truffle-1234", token: str | None = "token") -> None:
        self.state = StoredState(last_used_device=device)
        self.token = token

    def get_token(self, _device: str) -> str | None:
        return self.token

    def app_id_for_device(self, _device: str) -> None:
        return None


class HealthyClient:
    def __init__(self, *_args, **_kwargs) -> None:
        self.app_uuid = None
        self.builder_started = False
        self.builder_discarded = False

    async def connect(self, timeout: float = 15.0) -> None:
        assert timeout > 0

    async def check_auth(self) -> bool:
        return True

    async def get_task_infos(self, *, max_before: int) -> list[dict]:
        assert max_before == 1
        return [{"task_id": "task-1"}]

    async def get_all_apps(self) -> list[object]:
        return [object(), object()]

    async def start_build(self) -> None:
        self.builder_started = True
        self.app_uuid = "build-1"

    async def discard(self) -> None:
        self.builder_discarded = True
        self.app_uuid = None

    async def close(self) -> None:
        pass


async def _resolved(_hostname: str) -> str:
    return "192.0.2.10"


async def _healthy_if2(_ip: str, _timeout: float) -> dict:
    return {
        "status": "ok",
        "message": "IF2 is available",
        "service": "if2",
        "model_count": 1,
    }


def _json_stdout(capsys) -> dict:
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_doctor_json_reports_each_service(capsys):
    args = SimpleNamespace(json=True, timeout=5.0, builder=False)

    with (
        patch("truffile.cli.doctor.resolve_mdns", _resolved),
        patch("truffile.cli.doctor.TruffleClient", HealthyClient),
        patch("truffile.cli.doctor._if2_check", _healthy_if2),
    ):
        result = asyncio.run(cmd_doctor(args, FakeStorage()))

    assert result == 0
    payload = _json_stdout(capsys)
    assert payload["healthy"] is True
    assert payload["checks"]["execution_context"]["mode"] == "computer"
    assert payload["checks"]["saved_session"]["status"] == "ok"
    assert payload["checks"]["task_convo"]["recent_task_count"] == 1
    assert payload["checks"]["if2"]["model_count"] == 1
    assert payload["checks"]["app_runtime"]["installed_app_count"] == 2
    assert payload["checks"]["builder"]["status"] == "skipped"


def test_doctor_builder_probe_discards_session(capsys):
    args = SimpleNamespace(json=True, timeout=5.0, builder=True)
    client = HealthyClient()

    with (
        patch("truffile.cli.doctor.resolve_mdns", _resolved),
        patch("truffile.cli.doctor.TruffleClient", return_value=client),
        patch("truffile.cli.doctor._if2_check", _healthy_if2),
    ):
        result = asyncio.run(cmd_doctor(args, FakeStorage()))

    assert result == 0
    assert client.builder_started is True
    assert client.builder_discarded is True
    assert _json_stdout(capsys)["checks"]["builder"]["status"] == "ok"


def test_doctor_without_device_returns_actionable_json(capsys):
    args = SimpleNamespace(json=True, timeout=5.0, builder=False)

    result = asyncio.run(cmd_doctor(args, FakeStorage(device=None, token=None)))

    assert result == 1
    payload = _json_stdout(capsys)
    assert payload["code"] == "health_checks_failed"
    assert payload["checks"]["saved_session"]["code"] == "device_required"
    assert "Symphony" in payload["checks"]["saved_session"]["next_action"]


def test_help_command_matches_help_flag(capsys):
    with patch.object(sys, "argv", ["truffile", "--help"]):
        with pytest.raises(SystemExit) as exc:
            _main()
    assert exc.value.code == 0
    flag_help = capsys.readouterr().out

    with patch.object(sys, "argv", ["truffile", "help"]):
        assert _main() == 0
    command_help = capsys.readouterr().out

    assert command_help == flag_help


def test_version_flag_reports_package_version(capsys):
    with patch.object(sys, "argv", ["truffile", "--version"]):
        with pytest.raises(SystemExit) as exc:
            _main()

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"truffile {__version__}"
