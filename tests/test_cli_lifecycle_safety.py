import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

from truffile.cli.apps import cmd_delete
from truffile.cli.create import cmd_create
from truffile.cli.validate import cmd_validate


class FakeMetadata:
    def __init__(self, name: str, bundle_id: str) -> None:
        self.name = name
        self.bundle_id = bundle_id
        self.description = ""


class FakeApp:
    def __init__(self, name: str, uuid: str, *, foreground: bool = True, background: bool = False) -> None:
        self.metadata = FakeMetadata(name, f"org.truffle.{name.lower().replace(' ', '.')}")
        self.uuid = uuid
        self._fields = {"foreground": foreground, "background": background}

    def HasField(self, name: str) -> bool:
        return self._fields.get(name, False)


class FakeClient:
    def __init__(self, apps: list[FakeApp], *, fail_uuid: str | None = None) -> None:
        self.apps = apps
        self.fail_uuid = fail_uuid
        self.deleted: list[str] = []

    async def connect(self) -> None:
        pass

    async def get_all_apps(self) -> list[FakeApp]:
        return self.apps

    async def delete_app(self, uuid: str) -> None:
        if uuid == self.fail_uuid:
            raise RuntimeError("delete failed")
        self.deleted.append(uuid)

    async def close(self) -> None:
        pass


class FakeStorage:
    def get_token(self, _device: str) -> str:
        return "token"

    def app_id_for_device(self, _device: str) -> None:
        return None


async def _resolved(_storage, *, quiet=False):
    return "truffle-1234", "192.0.2.10"


def _run_delete(args, client: FakeClient) -> int:
    with (
        patch("truffile.cli.apps._resolve_connected_device", _resolved),
        patch("truffile.cli.apps.TruffleClient", return_value=client),
    ):
        return asyncio.run(cmd_delete(args, FakeStorage()))


def _json_stdout(capsys) -> dict:
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_create_json_returns_paths_and_next_action(tmp_path, capsys):
    args = SimpleNamespace(
        name="agent-app",
        path=str(tmp_path),
        json=True,
        non_interactive=True,
    )

    with patch("truffile.cli.create._load_stock_icon_bytes", return_value=(b"png", "memory")):
        result = cmd_create(args)

    assert result == 0
    payload = _json_stdout(capsys)
    assert payload["status"] == "ok"
    assert payload["app"]["name"] == "agent-app"
    assert set(payload["files"]) == {
        "truffile.yaml",
        "agent_app_foreground.py",
        "agent_app_background.py",
        "icon.png",
    }
    assert payload["next_action"].endswith("--json")


def test_create_json_requires_name(capsys):
    result = cmd_create(SimpleNamespace(
        name=None,
        path=None,
        json=True,
        non_interactive=True,
    ))

    assert result == 1
    assert _json_stdout(capsys)["code"] == "input_required"


def test_validate_json_reports_success_and_errors(tmp_path, capsys):
    missing = tmp_path / "missing"

    result = cmd_validate(SimpleNamespace(path=str(missing), json=True))

    assert result == 1
    assert _json_stdout(capsys)["code"] == "invalid_path"


def test_delete_dry_run_does_not_mutate(capsys):
    client = FakeClient([FakeApp("Alpha App", "uuid-alpha")])
    args = SimpleNamespace(
        selection=["alpha-app"],
        dry_run=True,
        yes=False,
        json=True,
        non_interactive=True,
    )

    result = _run_delete(args, client)

    assert result == 0
    assert client.deleted == []
    payload = _json_stdout(capsys)
    assert payload["dry_run"] is True
    assert payload["apps"][0]["uuid"] == "uuid-alpha"


def test_delete_json_requires_explicit_confirmation(capsys):
    client = FakeClient([FakeApp("Alpha App", "uuid-alpha")])
    args = SimpleNamespace(
        selection=["uuid-alpha"],
        dry_run=False,
        yes=False,
        json=True,
        non_interactive=True,
    )

    result = _run_delete(args, client)

    assert result == 1
    assert client.deleted == []
    payload = _json_stdout(capsys)
    assert payload["code"] == "confirmation_required"
    assert payload["apps"][0]["name"] == "Alpha App"


def test_delete_yes_returns_deleted_apps(capsys):
    client = FakeClient([FakeApp("Alpha App", "uuid-alpha")])
    args = SimpleNamespace(
        selection=["Alpha App"],
        dry_run=False,
        yes=True,
        json=True,
        non_interactive=True,
    )

    result = _run_delete(args, client)

    assert result == 0
    assert client.deleted == ["uuid-alpha"]
    payload = _json_stdout(capsys)
    assert payload["status"] == "ok"
    assert payload["deleted"][0]["uuid"] == "uuid-alpha"


def test_delete_partial_failure_is_structured(capsys):
    client = FakeClient(
        [FakeApp("Alpha App", "uuid-alpha"), FakeApp("Beta App", "uuid-beta")],
        fail_uuid="uuid-beta",
    )
    args = SimpleNamespace(
        selection=["all"],
        dry_run=False,
        yes=True,
        json=True,
        non_interactive=True,
    )

    result = _run_delete(args, client)

    assert result == 1
    payload = _json_stdout(capsys)
    assert payload["code"] == "delete_failed"
    assert payload["deleted"][0]["uuid"] == "uuid-alpha"
    assert payload["failures"][0]["uuid"] == "uuid-beta"


def test_delete_invalid_selection_is_structured(capsys):
    client = FakeClient([FakeApp("Alpha App", "uuid-alpha")])
    args = SimpleNamespace(
        selection=["missing-app"],
        dry_run=False,
        yes=True,
        json=True,
        non_interactive=True,
    )

    result = _run_delete(args, client)

    assert result == 1
    assert client.deleted == []
    assert _json_stdout(capsys)["code"] == "invalid_selection"


def test_delete_invalid_selection_never_prompts_from_a_tty(monkeypatch, capsys):
    client = FakeClient([FakeApp("Alpha App", "uuid-alpha")])
    args = SimpleNamespace(
        selection=["missing-app"],
        dry_run=False,
        yes=True,
        json=True,
        non_interactive=True,
    )
    monkeypatch.setattr("truffile.cli.apps.sys.stdin.isatty", lambda: True)

    def unexpected_prompt(_prompt: str) -> str:
        raise AssertionError("machine mode must not prompt")

    monkeypatch.setattr("builtins.input", unexpected_prompt)

    result = _run_delete(args, client)

    assert result == 1
    assert client.deleted == []
    assert _json_stdout(capsys)["code"] == "invalid_selection"


def test_delete_interactive_cancel_does_not_mutate(monkeypatch):
    client = FakeClient([FakeApp("Alpha App", "uuid-alpha")])
    args = SimpleNamespace(
        selection=["alpha-app"],
        dry_run=False,
        yes=False,
        json=False,
        non_interactive=False,
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    monkeypatch.setattr("truffile.cli.apps.sys.stdin.isatty", lambda: True)

    result = _run_delete(args, client)

    assert result == 0
    assert client.deleted == []
