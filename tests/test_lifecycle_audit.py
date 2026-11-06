import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from truffle.app.app_pb2 import App, AppConnection
from truffle.os.app_queries_pb2 import UpdateAppConnectionResponse
from truffile.cli.apps import _app_summary, cmd_list
from truffile.cli.connections import select_app, select_connection, cmd_connections
from truffile.cli.connect import cmd_connect
from truffile.cli.deploy import _check_existing_app
from truffile.cli.device_names import normalize_device_name
from truffile.transport.client import TruffleClient
from truffile.storage import StorageService, StoredState


def app():
    value = App(uuid="app-a", connection_capability=2)
    value.metadata.name = "Mail"
    value.metadata.bundle_id = "org.test.mail"
    value.foreground.SetInParent()
    account = value.connections.add(connection_id="account-a", alias="Work", is_default=True, status=1)
    account.permission.flags = 1
    account.permission.auto_review_notes = "Existing review policy"
    value.connections.add(connection_id="account-b", alias="Personal", status=1)
    return value


@pytest.mark.parametrize("raw", ["6272", "6-2-7-2", "truffle-6272", "TRUFFLE-6272.local", "truffle-6272.local.", " truffle-6272 "])
def test_device_spelling_normalizes(raw):
    assert normalize_device_name(raw) == "truffle-6272"


def test_connect_number_uses_canonical_saved_session(monkeypatch):
    from truffile.cli import connect
    client = SimpleNamespace(connect=AsyncMock(), check_auth=AsyncMock(return_value=True), close=AsyncMock())
    resolve = AsyncMock(return_value="192.0.2.10")
    monkeypatch.setattr(connect, "probe_in_container_device", lambda: None)
    monkeypatch.setattr(connect, "resolve_mdns", resolve)
    monkeypatch.setattr(connect, "TruffleClient", lambda *a: client)
    used=[]
    storage = SimpleNamespace(get_token=lambda name: "token" if name == "truffle-6272" else None, set_last_used=used.append)
    assert asyncio.run(cmd_connect(SimpleNamespace(device="6272"), storage)) == 0
    assert resolve.call_args.args == ("truffle-6272.local",)
    assert used == ["truffle-6272"]


def test_app_listing_includes_saved_connection_authority():
    row = _app_summary(app())
    assert row["bundle_id"] == "org.test.mail"
    assert row["connections"][0]["permission"]["flags"] == 1
    assert row["connection_capability"] == "APP_CONNECTION_CAPABILITY_MULTI"


def test_connection_selection_is_exact_and_rejects_ambiguity():
    value = app()
    assert select_app([value], "org.test.mail") is value
    assert select_connection(value, "default").connection_id == "account-a"
    assert select_connection(value, "personal").connection_id == "account-b"
    value.connections[1].alias = "Work"
    with pytest.raises(ValueError, match="found 2"):
        select_connection(value, "Work")
    with pytest.raises(ValueError, match="found 0"):
        select_app([value], "Mai")


def test_permission_and_rename_rpcs_are_separate():
    async def scenario():
        client = TruffleClient("localhost", "token")
        client.stub = SimpleNamespace(Apps_UpdateConnection=AsyncMock(return_value=UpdateAppConnectionResponse(app=app())))
        await client.update_connection("app-a", "account-a", permission_flags=11, auto_review_notes="New policy")
        req = client.stub.Apps_UpdateConnection.call_args.args[0]
        assert req.permission.flags == 11
        assert req.permission.auto_review_notes == "New policy"
        assert not req.HasField("alias")
        assert client.stub.Apps_UpdateConnection.call_args.kwargs["metadata"] == [("session", "token")]
        await client.update_connection("app-a", "account-a", alias="Work")
        req = client.stub.Apps_UpdateConnection.call_args.args[0]
        assert req.alias == "Work" and not req.HasField("permission")
        for flags in (True, 4, 2, 99, -1):
            with pytest.raises(ValueError):
                await client.update_connection("app-a", "account-a", permission_flags=flags)
        with pytest.raises(ValueError):
            await client.update_connection("app-a", "account-a", alias="x", permission_flags=1)
    asyncio.run(scenario())


def test_permission_cli_preserves_notes_and_other_account(monkeypatch, capsys):
    from truffile.cli import connections
    value=app()
    client=SimpleNamespace(connect=AsyncMock(), get_all_apps=AsyncMock(return_value=[value]), update_connection=AsyncMock(return_value=value), close=AsyncMock())
    monkeypatch.setattr(connections, "_resolve_connected_device", AsyncMock(return_value=("truffle-test", "192.0.2.2")))
    monkeypatch.setattr(connections, "TruffleClient", lambda *a, **k: client)
    storage=SimpleNamespace(get_token=lambda _: "token", app_id_for_device=lambda _: None)
    args=SimpleNamespace(app="Mail", connection="Work", connections_command="permissions", mode="auto-review", notes=None, json=True)
    assert asyncio.run(cmd_connections(args, storage)) == 0
    assert client.update_connection.call_args.args == ("app-a", "account-a")
    assert client.update_connection.call_args.kwargs == {"permission_flags":11,"auto_review_notes":"Existing review policy"}
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    client.close.assert_awaited_once()


def test_connection_busy_reports_rpc_error_without_retry(monkeypatch, capsys):
    import grpc
    from truffile.cli import connections

    failure = grpc.aio.AioRpcError(
        grpc.StatusCode.INVALID_ARGUMENT, (), (),
        "another app operation is already in progress; do not retry",
    )
    client = SimpleNamespace(
        connect=AsyncMock(), get_all_apps=AsyncMock(return_value=[app()]),
        update_connection=AsyncMock(side_effect=failure), close=AsyncMock(),
    )
    monkeypatch.setattr(connections, "_resolve_connected_device", AsyncMock(return_value=("test", "localhost")))
    monkeypatch.setattr(connections, "TruffleClient", lambda *a, **k: client)
    storage = SimpleNamespace(get_token=lambda _: "token", app_id_for_device=lambda _: None)
    args = SimpleNamespace(app="Mail", connection="Work", connections_command="rename", alias="New", json=True)

    assert asyncio.run(cmd_connections(args, storage)) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["rpc_code"] == "INVALID_ARGUMENT"
    assert result["error"] == failure.details()
    client.update_connection.assert_awaited_once()
    client.close.assert_awaited_once()


def test_builder_never_deletes_existing_app(monkeypatch, capsys):
    from truffile.cli import deploy
    client=SimpleNamespace(connect=AsyncMock(),get_all_apps=AsyncMock(return_value=[app()]),delete_app=AsyncMock(),close=AsyncMock())
    monkeypatch.setattr(deploy,"TruffleClient",lambda *a,**k:client)
    storage=SimpleNamespace(app_id_for_device=lambda _:None)
    result=asyncio.run(_check_existing_app(address="localhost",token="token",storage=storage,device="test",bundle_id="org.test.mail",json_out=True))
    assert result[0] == 1
    assert json.loads(capsys.readouterr().out)["error"] == "update_required"
    client.delete_app.assert_not_awaited()


def test_devices_json_does_not_expose_credentials(capsys):
    storage=SimpleNamespace(list_devices=lambda:["truffle-a"],state=SimpleNamespace(last_used_device="truffle-a"))
    assert cmd_list(SimpleNamespace(what="devices",json=True),storage)==0
    assert json.loads(capsys.readouterr().out)=={"devices":[{"name":"truffle-a","active":True}]}


def test_storage_replaces_existing_world_readable_state_privately(tmp_path):
    storage=StorageService.__new__(StorageService)
    storage.storage_dir=tmp_path
    storage.state_file=tmp_path/"state.json"
    storage.state=StoredState()
    storage.state_file.write_text("{}")
    storage.state_file.chmod(0o644)
    storage.set_token("truffle-test","private-token")
    assert storage.state_file.stat().st_mode & 0o777 == 0o600
    assert json.loads(storage.state_file.read_text())["devices"][0]["token"] == "private-token"
    assert not list(tmp_path.glob(".state-*"))


def test_modern_manifest_fails_before_builder_can_drop_connection_scopes(tmp_path):
    from truffile.cli.create import _sample_truffile_yaml
    from truffile.schema import validate_app_dir
    import yaml
    data=yaml.safe_load(_sample_truffile_yaml("Audit", "audit"))
    data.update(truffile_version=4,connections="multi")
    data["metadata"]["resource_profile"]="max"
    data["steps"]=[]
    (tmp_path/"truffile.yaml").write_text(yaml.safe_dump(data))
    valid,_,_,_,errors=validate_app_dir(tmp_path)
    assert not valid
    assert any("connection" in e for e in errors)
    assert any("resource_profile" in e for e in errors)


def test_unpaired_script_does_not_prompt_and_emits_one_json(monkeypatch, capsys):
    import sys
    from truffile.cli import _main
    monkeypatch.setattr("truffile.storage.StorageService", lambda: SimpleNamespace(state=StoredState()))
    monkeypatch.setattr("truffile.cli.in_container.probe_in_container_device", lambda: None)
    monkeypatch.setattr(sys, "argv", ["truffile", "convo", "--json", "hello"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert _main() == 1
    assert json.loads(capsys.readouterr().out)["error"] == "not_connected"


def test_delete_failure_returns_failure(monkeypatch):
    from truffile.cli import apps
    client=SimpleNamespace(connect=AsyncMock(),get_all_apps=AsyncMock(return_value=[app()]),delete_app=AsyncMock(side_effect=RuntimeError("unavailable")),close=AsyncMock())
    monkeypatch.setattr(apps,"_resolve_connected_device",AsyncMock(return_value=("test","localhost")))
    monkeypatch.setattr(apps,"TruffleClient",lambda *a,**k:client)
    storage=SimpleNamespace(get_token=lambda _:"token",app_id_for_device=lambda _:None)
    assert asyncio.run(apps.cmd_delete(SimpleNamespace(selection=["app-a"]),storage)) == 1
