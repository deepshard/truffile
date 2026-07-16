import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from truffile.cli import build_parser
from truffile.cli.apps import cmd_list
from truffile.cli.connect import cmd_connect
from truffile.cli.infer import _run_oneshot
from truffile.cli.load import cmd_load
from truffile.storage import StoredDevice, StoredState


class MemoryStorage:
    def __init__(self, *, token: str | None = None) -> None:
        devices = [StoredDevice(name="truffle-1234", token=token)] if token else []
        self.state = StoredState(
            devices=devices,
            last_used_device="truffle-1234" if token else None,
        )

    def get_token(self, device: str) -> str | None:
        for saved in self.state.devices:
            if saved.name == device:
                return saved.token
        return None

    def list_devices(self) -> list[str]:
        return [device.name for device in self.state.devices]

    def save(self) -> None:
        pass


def _json_stdout(capsys) -> dict:
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_machine_flags_parse_without_prompts():
    parser = build_parser()

    scan = parser.parse_args(["scan", "--json", "--non-interactive"])
    connect = parser.parse_args([
        "connect",
        "truffle-1234",
        "--json",
        "--non-interactive",
        "--approval-timeout",
        "10",
    ])

    assert scan.json is True
    assert scan.non_interactive is True
    assert connect.json is True
    assert connect.non_interactive is True
    assert connect.approval_timeout == 10


def test_list_devices_json_is_parseable(capsys):
    storage = MemoryStorage(token="token")

    result = cmd_list(SimpleNamespace(what="devices", json=True), storage)

    assert result == 0
    payload = _json_stdout(capsys)
    assert payload == {
        "schema_version": "1",
        "status": "ok",
        "devices": [{"name": "truffle-1234", "active": True}],
    }


def test_load_existing_resources_keeps_json_stdout_clean(tmp_path, capsys):
    target = tmp_path / "truffile" / "skills"
    target.mkdir(parents=True)

    result = cmd_load(SimpleNamespace(
        what="skills",
        path=str(tmp_path),
        force=False,
        json=True,
    ))

    assert result == 0
    payload = _json_stdout(capsys)
    assert payload["status"] == "ok"
    assert payload["resources"][0]["copied"] is False
    assert payload["cli_version"] == payload["resource_version"]


def test_connect_json_reports_missing_symphony_user_id(capsys):
    storage = MemoryStorage()
    args = SimpleNamespace(
        device="truffle-1234",
        user_id=None,
        json=True,
        non_interactive=True,
        approval_timeout=10.0,
    )

    async def resolved(_hostname: str) -> str:
        return "192.0.2.10"

    with patch("truffile.cli.connect.resolve_mdns", resolved):
        result = asyncio.run(cmd_connect(args, storage))

    assert result == 1
    payload = _json_stdout(capsys)
    assert payload["code"] == "user_id_required"
    assert "Symphony Settings" in payload["next_action"]


def test_infer_json_preserves_if2_http_failure(capsys):
    storage = MemoryStorage(token="token")
    args = SimpleNamespace(
        quiet=True,
        json=True,
        list_models=True,
        timeout=5.0,
    )
    request = httpx.Request("GET", "http://192.0.2.10/if2/v1/models")
    response = httpx.Response(503, request=request)
    failure = httpx.HTTPStatusError("service unavailable", request=request, response=response)

    async def resolved(_storage, *, quiet=False):
        return "truffle-1234", "192.0.2.10"

    with (
        patch("truffile.cli.infer._resolve_connected_device", resolved),
        patch("truffile.cli.infer._fetch_models_payload", side_effect=failure),
    ):
        result = asyncio.run(_run_oneshot(args, storage))

    assert result == 1
    payload = _json_stdout(capsys)
    assert payload["code"] == "service_unavailable"
    assert payload["service"] == "if2"
    assert payload["http_status"] == 503
    assert payload["retryable"] is True
