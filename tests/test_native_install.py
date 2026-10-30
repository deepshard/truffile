import asyncio
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import grpc
import httpx
import pytest
from truffle.app.app_pb2 import App
from truffle.os.installer_pb2 import AppInstallResponse, AppInstallUserAction
from truffile.deploy.native import prepare_bundle, install_native
from truffile.cli.connections import choose_app, choose_connection
from truffile.cli.native import InstallPrompts, InteractionRequired


def fixture(path):
    (path / "truffile.yaml").write_text("truffile_version: 6\nconnections: multi\nmetadata:\n  name: Test\n  bundle_id: org.test.native\n")
    (path / "app.py").write_text("print('hello')\n")
    return path


def test_bundle_preserves_native_manifest_and_excludes_local_secrets(tmp_path):
    fixture(tmp_path)
    (tmp_path / ".env").write_text("secret")
    (tmp_path / "scratch.txt").write_text("ignored")
    (tmp_path / ".truffleignore").write_text("scratch.txt\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "secret").write_text("secret")
    answers = tmp_path / "answers.json"
    answers.write_text('{"password":"never upload"}')
    with prepare_bundle(tmp_path, exclude_paths=[answers]) as first, prepare_bundle(tmp_path, exclude_paths=[answers]) as second:
        assert first.sha256 == second.sha256
        with zipfile.ZipFile(first.path) as data:
            assert set(data.namelist()) == {"truffile.yaml", "app.py"}
            assert data.read("truffile.yaml") == (tmp_path / "truffile.yaml").read_bytes()


def test_bundle_rejects_path_escape_and_symlinks(tmp_path):
    archive = tmp_path / "unsafe.truffle"
    with zipfile.ZipFile(archive, "w") as data:
        data.writestr("../secret", "x")
    with pytest.raises(ValueError, match="unsafe"):
        with prepare_bundle(archive):
            pass
    fixture(tmp_path)
    (tmp_path / "link").symlink_to(tmp_path / "app.py")
    with pytest.raises(ValueError, match="symlink"):
        with prepare_bundle(tmp_path):
            pass


class Stream:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.writes = []
        self.cancelled = False

    async def write(self, request):
        self.writes.append(request)

    async def read(self):
        return next(self.responses, grpc.aio.EOF)

    def cancel(self):
        self.cancelled = True


def client(stream, supported=True):
    return SimpleNamespace(
        address="device:80", _metadata=[("session", "private")],
        stub=SimpleNamespace(Apps_InstallApp=Mock(return_value=stream)),
        supports_developer_uploads=AsyncMock(return_value=supported),
    )


@pytest.mark.parametrize("mode", ["install", "update", "replace"])
def test_native_upload_uses_correct_mode_and_never_writes_after_finish(tmp_path, monkeypatch, mode):
    fixture(tmp_path)
    upload = AppInstallResponse()
    upload.install_modal.upload_file_modal.upload_uri_path = "/containers/audit/source/upload"
    text = AppInstallResponse()
    text.install_modal.text_fields_modal.fields["api_key"].is_password = True
    finish = AppInstallResponse()
    finish.install_modal.finish_modal.app_uuid = "installed"
    stream = Stream([upload, text, finish])
    c = client(stream)
    received = []
    real_http = httpx.AsyncClient
    async def transport(request):
        assert request.url.host == "device"
        assert request.headers["session"] == "private"
        received.append(await request.aread())
        return httpx.Response(200)
    monkeypatch.setattr("truffile.deploy.native.httpx.AsyncClient", lambda **kw: real_http(transport=httpx.MockTransport(transport)))
    response = AppInstallUserAction()
    response.text_fields.field_responses["api_key"] = "fake-secret"
    with prepare_bundle(tmp_path) as bundle:
        result = asyncio.run(install_native(c, mode=mode, app_uuid="installed", bundle=bundle, handle_modal=AsyncMock(return_value=response)))
    assert result["app_uuid"] == "installed"
    assert len(received) == 1
    assert len(stream.writes) == 2
    first = stream.writes[0]
    assert first.HasField("start_update" if mode == "update" else "start_new")
    assert first.start_new.replace_app_uuid == ("installed" if mode == "replace" else "")
    if mode != "install":
        assert ("truffile-developer-upload", "1") in c.stub.Apps_InstallApp.call_args.kwargs["metadata"]
    assert stream.cancelled


@pytest.mark.parametrize("mode", ["update", "replace"])
def test_old_firmware_is_rejected_before_any_mutation(tmp_path, mode):
    c = client(Stream([]), supported=False)
    with prepare_bundle(fixture(tmp_path)) as bundle, pytest.raises(RuntimeError, match="no app was changed"):
        asyncio.run(install_native(c, mode=mode, bundle=bundle, app_uuid="old", handle_modal=AsyncMock()))
    c.stub.Apps_InstallApp.assert_not_called()


@pytest.mark.parametrize("mode", ["add", "reconnect"])
def test_account_operations_target_exact_identity(mode):
    finish = AppInstallResponse()
    finish.install_modal.finish_modal.app_uuid = "app"
    finish.install_modal.finish_modal.connection_id = "account"
    stream = Stream([finish])
    asyncio.run(install_native(client(stream), mode=mode, app_uuid="app", connection_id="account", handle_modal=AsyncMock()))
    request = stream.writes[0]
    start = request.start_add_connection if mode == "add" else request.start_reconnect
    assert start.app_uuid == "app"
    if mode == "reconnect":
        assert start.connection_id == "account"
    assert len(stream.writes) == 1


def test_disconnect_requests_abort_without_retrying():
    stream = Stream([])
    c = client(stream)
    with pytest.raises(RuntimeError, match="before completion"):
        asyncio.run(install_native(c, mode="add", app_uuid="app", handle_modal=AsyncMock()))
    assert stream.writes[-1].user_action.HasField("abort")
    c.stub.Apps_InstallApp.assert_called_once()
    assert stream.cancelled


def test_account_setup_rejects_an_uploaded_bundle_before_mutation(tmp_path):
    c = client(Stream([]))
    with prepare_bundle(fixture(tmp_path)) as bundle, pytest.raises(ValueError, match="installed bundle"):
        asyncio.run(install_native(c, mode="add", app_uuid="app", bundle=bundle, handle_modal=AsyncMock()))
    c.stub.Apps_InstallApp.assert_not_called()


def test_friendly_account_picker_and_script_ambiguity(monkeypatch):
    app = App(uuid="app")
    app.metadata.name = "Google"
    app.connections.add(connection_id="work", alias="Work")
    app.connections.add(connection_id="personal", alias="Personal")
    args = SimpleNamespace(json=False, non_interactive=False)
    monkeypatch.setattr("truffile.cli.prompts.interactive", lambda _: True)
    monkeypatch.setattr("truffile.cli.prompts.prompt", AsyncMock(return_value="2"))
    assert asyncio.run(choose_app([app], "google", args)).uuid == "app"
    assert asyncio.run(choose_connection(app, None, args)).connection_id == "personal"
    monkeypatch.setattr("truffile.cli.prompts.interactive", lambda _: False)
    with pytest.raises(ValueError, match="Specify an exact"):
        asyncio.run(choose_connection(app, None, args))
    assert asyncio.run(choose_connection(app, "Work", args)).connection_id == "work"


def test_password_file_is_used_without_printing_values(tmp_path, capsys):
    path = tmp_path / "answers.json"
    path.write_text(json.dumps({"api_key": "private-value"}))
    modal = AppInstallResponse().install_modal
    modal.text_fields_modal.fields["api_key"].is_password = True
    ui = InstallPrompts(SimpleNamespace(answers_file=str(path), json=True), "device:80")
    action = asyncio.run(ui(modal))
    assert action.text_fields.field_responses["api_key"] == "private-value"
    assert "private-value" not in str(capsys.readouterr())


def test_missing_form_input_is_actionable_in_scripts():
    modal = AppInstallResponse().install_modal
    modal.text_fields_modal.fields["email"].label = "Email"
    ui = InstallPrompts(SimpleNamespace(json=True), "device:80")
    with pytest.raises(InteractionRequired, match="answers-file"):
        asyncio.run(ui(modal))


@pytest.mark.parametrize("value,valid", [
    ("https://callback.example/?code=approved&state=pending", True),
    ("https://callback.example/?code=approved", False),
    ("https://callback.example/?code=approved&state=wrong", False),
])
def test_native_oauth_requires_matching_state_in_pasted_urls(monkeypatch, value, valid):
    monkeypatch.setattr("truffile.cli.native.interactive", lambda _: True)
    monkeypatch.setattr("truffile.cli.native.prompt", AsyncMock(return_value=value))
    modal = AppInstallResponse().install_modal
    modal.oauth_modal.auth_url = "https://provider.example/authorize"
    modal.oauth_modal.state = "pending"
    ui = InstallPrompts(SimpleNamespace(), "device:80")
    if valid:
        action = asyncio.run(ui(modal))
        assert action.oauth.code == "approved" and action.oauth.state == "pending"
    else:
        with pytest.raises(RuntimeError, match="state"):
            asyncio.run(ui(modal))


def test_loopback_oauth_rejects_wrong_state_then_completes(monkeypatch):
    import os
    import socket
    if os.name != "posix":
        pytest.skip("automatic loopback is currently POSIX only")
    monkeypatch.setattr("truffile.cli.native.interactive", lambda _: True)
    async def scenario():
        ready = asyncio.Event()
        async def pending_paste(*args, **kwargs):
            ready.set()
            await asyncio.Future()
        monkeypatch.setattr("truffile.cli.native.prompt", pending_paste)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        modal = AppInstallResponse().install_modal
        modal.oauth_modal.auth_url = "https://provider.example/authorize"
        modal.oauth_modal.state = "pending"
        modal.oauth_modal.loopback_callback.redirect_uri = f"http://127.0.0.1:{port}/callback"
        task = asyncio.create_task(InstallPrompts(SimpleNamespace(), "device:80")(modal))
        try:
            await asyncio.wait_for(ready.wait(), 2)
            async with httpx.AsyncClient(trust_env=False) as http:
                bad = await http.get(f"http://127.0.0.1:{port}/callback?code=bad&state=wrong")
                assert bad.status_code == 400 and not task.done()
                good = await http.get(f"http://127.0.0.1:{port}/callback?code=approved&state=pending")
                assert good.status_code == 200
            action = await asyncio.wait_for(task, 2)
            assert action.oauth.code == "approved"
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize("argv,attribute,expected", [
    (["rename", "Google", "Work"], "alias", "Work"),
    (["permissions", "Google", "read-only"], "mode", "read-only"),
    (["reconnect", "Google"], "connections_command", "reconnect"),
    (["delete", "Google"], "connections_command", "delete"),
])
def test_parser_allows_omitting_account_for_picker(monkeypatch, argv, attribute, expected):
    import sys
    from truffile.cli import _main
    from truffile.storage import StoredState
    command = AsyncMock(return_value=0)
    monkeypatch.setattr("truffile.cli.connections.cmd_connections", command)
    monkeypatch.setattr("truffile.storage.StorageService", lambda: SimpleNamespace(state=StoredState(last_used_device="test")))
    monkeypatch.setattr("truffile.cli.in_container.probe_in_container_device", lambda: None)
    monkeypatch.setattr(sys, "argv", ["truffile", "connections", *argv])
    assert _main() == 0
    args = command.call_args.args[0]
    assert args.connection is None
    assert getattr(args, attribute) == expected
