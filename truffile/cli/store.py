from __future__ import annotations

import asyncio
import contextlib
import getpass
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

from truffle.app.app_pb2 import App
from truffle.os.installer_pb2 import (
    APP_INSTALL_SOURCE_TYPE_URL,
    AppInstallRequest,
    AppInstallSource,
)
from truffile.client import TruffleClient
from truffile.storage import StorageService
from truffile.store.manifest import (
    StoreApp,
    StoreRelease,
    classify_bundle_bytes,
    fetch_bundle_bytes,
    fetch_store_apps,
    find_store_app,
)

from .connect import _resolve_connected_device
from .ui import C, CHECK, DOT, Spinner, error, success


BROWSER_UNSUPPORTED_MESSAGE = (
    "This app uses the browser runtime. Please go to Symphony Settings to install this app; "
    "browser apps are not supported through truffile yet."
)
UPDATE_REAUTH_MESSAGE = "Update needs reauthentication. Please go to Settings to update this app."


class _NoopSpinner:
    def start(self) -> None:
        return None

    def stop(self, success: bool = True) -> None:
        return None

    def fail(self, message: str | None = None) -> None:
        return None


def _spinner(message: str, *, enabled: bool) -> Spinner | _NoopSpinner:
    return Spinner(message) if enabled else _NoopSpinner()


@dataclass(frozen=True)
class StoreRow:
    app: StoreApp
    installed_app: App | None
    status: str
    installed_sha: str

    @property
    def update_available(self) -> bool:
        return self.status == "update available"


async def _connect_client(storage: StorageService) -> TruffleClient | None:
    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return None
    token = storage.get_token(device)
    if not token:
        error(f"No token for {device}")
        print(f"  {C.DIM}Run: truffile connect {device}{C.RESET}")
        return None
    client = TruffleClient(f"{ip}:80", token=token, app_id=storage.app_id_for_device(device))
    await client.connect()
    return client


def _installed_release_sha(app: App) -> str:
    try:
        if app.HasField("installed_bundle") and app.installed_bundle.HasField("release"):
            return app.installed_bundle.release.bundle_sha256.strip()
    except ValueError:
        return ""
    return ""


def merge_store_rows(store_apps: list[StoreApp], installed_apps: list[App]) -> list[StoreRow]:
    by_bundle_id = {
        app.metadata.bundle_id.strip(): app
        for app in installed_apps
        if app.metadata.bundle_id.strip()
    }
    rows: list[StoreRow] = []
    for app in store_apps:
        installed = by_bundle_id.get(app.bundle_id)
        installed_sha = _installed_release_sha(installed) if installed else ""
        latest_sha = app.latest_sha
        if installed is None:
            status = "not installed"
        elif latest_sha and installed_sha and latest_sha != installed_sha:
            status = "update available"
        elif latest_sha and not installed_sha:
            status = "installed"
        else:
            status = "installed"
        rows.append(StoreRow(app=app, installed_app=installed, status=status, installed_sha=installed_sha))
    return rows


def _json_dump(payload) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _json_print(payload) -> None:
    print(_json_dump(payload))


def _json_status(status: str) -> str:
    return status.replace(" ", "_")


def _row_to_json(row: StoreRow) -> dict:
    app = row.app
    payload = {
        "name": app.name,
        "id": app.bundle_id,
        "status": _json_status(row.status),
    }
    if row.installed_app:
        payload["app_uuid"] = row.installed_app.uuid
    if app.latest_release and app.latest_release.display_version:
        payload["version"] = app.latest_release.display_version
    kind = _capabilities(app)
    if kind != "-":
        payload["kind"] = kind
    if app.tools_count:
        payload["tools"] = app.tools_count
    return payload


def _app_result(app: StoreApp, status: str, *, app_uuid: str = "", error_message: str = "") -> dict:
    payload = {
        "status": status,
        "name": app.name,
        "id": app.bundle_id,
    }
    if app_uuid:
        payload["app_uuid"] = app_uuid
    if error_message:
        payload["error"] = error_message
    return payload


def _capabilities(app: StoreApp) -> str:
    if app.provides_foreground and app.provides_background:
        return "fg+bg"
    if app.provides_foreground:
        return "fg"
    if app.provides_background:
        return "bg"
    return "-"


def _print_store_rows(rows: list[StoreRow]) -> None:
    print()
    print(f"{C.BOLD}Truffle App Store{C.RESET}")
    print()
    if not rows:
        print(f"  {C.DIM}No apps found{C.RESET}")
        return
    name_w = min(max(len(row.app.name) for row in rows), 28)
    status_w = max(len(row.status) for row in rows)
    print(
        f"  {C.DIM}{'App':<{name_w}}  {'Status':<{status_w}}  {'Kind':<5}  {'Tools':>5}  Version{C.RESET}"
    )
    for row in rows:
        marker = CHECK if row.status == "installed" else "!"
        color = C.GREEN if row.status == "installed" else C.YELLOW if row.update_available else C.CYAN
        version = row.app.latest_release.display_version if row.app.latest_release else ""
        print(
            f"  {color}{marker}{C.RESET} "
            f"{row.app.name[:name_w]:<{name_w}}  "
            f"{row.status:<{status_w}}  "
            f"{_capabilities(row.app):<5}  "
            f"{row.app.tools_count:>5}  "
            f"{C.DIM}{version}{C.RESET}"
        )


async def cmd_list_store(args, storage: StorageService) -> int:
    json_mode = bool(getattr(args, "json", False))
    spinner = _spinner("Fetching app store manifest", enabled=not json_mode)
    spinner.start()
    try:
        store_apps = await fetch_store_apps()
        spinner.stop(success=True)
    except Exception as exc:
        spinner.fail(f"Failed to fetch app store manifest: {exc}")
        return 1

    spinner = _spinner("Connecting to device", enabled=not json_mode)
    spinner.start()
    client = None
    try:
        client = await _connect_client(storage)
        if client is None:
            spinner.fail("Could not connect to device")
            return 1
        installed_apps = await client.get_all_apps()
        spinner.stop(success=True)
    except Exception as exc:
        spinner.fail(f"Failed to read installed apps: {exc}")
        return 1
    finally:
        if client:
            await client.close()

    rows = merge_store_rows(store_apps, installed_apps)
    rows.sort(key=lambda row: row.app.name.lower())
    if json_mode:
        _json_print([_row_to_json(row) for row in rows])
    else:
        _print_store_rows(rows)
    return 0


def _apply_release(target, release: StoreRelease | None) -> None:
    if release is None:
        return
    target.bundle_sha256 = release.bundle_sha256
    target.bundle_url = release.bundle_url
    target.display_version = release.display_version
    target.release_notes = release.release_notes
    if release.released_at:
        try:
            dt = datetime.fromisoformat(release.released_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            target.released_at.FromDatetime(dt.astimezone(timezone.utc))
        except ValueError:
            pass


def build_url_source(app: StoreApp) -> AppInstallSource:
    source = AppInstallSource()
    source.source_type = APP_INSTALL_SOURCE_TYPE_URL
    source.url = app.effective_bundle_url
    _apply_release(source.release, app.latest_release)
    return source


async def _ensure_cli_supported(app: StoreApp) -> None:
    if not app.effective_bundle_url:
        raise RuntimeError("store app has no bundle URL")
    bundle = await fetch_bundle_bytes(app.effective_bundle_url)
    classification = classify_bundle_bytes(bundle)
    if classification.is_browser:
        raise RuntimeError(BROWSER_UNSUPPORTED_MESSAGE)


def parse_oauth_callback(raw: str) -> tuple[str, str]:
    value = raw.strip()
    if not value:
        return "", ""
    parsed = urlparse(value)
    if parsed.query:
        qs = parse_qs(parsed.query)
        code = (qs.get("code") or [""])[0].strip()
        state = (qs.get("state") or [""])[0].strip()
        return code, state
    return value, ""


def _parse_field_args(values: list[str] | None) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw in values or []:
        if "=" not in raw:
            raise ValueError(f"field must be KEY=VALUE: {raw}")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"field must be KEY=VALUE: {raw}")
        fields[key] = value
    return fields


class _InstallRequestStream:
    def __init__(self, first: AppInstallRequest) -> None:
        self._queue: asyncio.Queue[AppInstallRequest | None] = asyncio.Queue()
        self._queue.put_nowait(first)

    def __aiter__(self) -> "_InstallRequestStream":
        return self

    async def __anext__(self) -> AppInstallRequest:
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def put(self, request: AppInstallRequest) -> None:
        await self._queue.put(request)

    async def close(self) -> None:
        await self._queue.put(None)


def _start_install_request(app: StoreApp) -> AppInstallRequest:
    req = AppInstallRequest()
    req.start_new.source.CopyFrom(build_url_source(app))
    return req


def _start_update_request(app: StoreApp, app_uuid: str) -> AppInstallRequest:
    req = AppInstallRequest()
    req.start_update.app_uuid = app_uuid
    req.start_update.source.CopyFrom(build_url_source(app))
    return req


async def _run_install_stream(
    *,
    client: TruffleClient,
    first_request: AppInstallRequest,
    mode: str,
    text_fields: dict[str, str] | None = None,
    no_interactive: bool = False,
    json_mode: bool = False,
) -> tuple[bool, str]:
    stream = _InstallRequestStream(first_request)
    app_uuid = ""
    supplied_fields = text_fields or {}
    terminal_result: tuple[bool, str] | None = None
    call = None

    async def _abort_with(message: str) -> None:
        nonlocal terminal_result
        if terminal_result is None:
            terminal_result = (False, message)
        req = AppInstallRequest()
        req.user_action.abort.SetInParent()
        await stream.put(req)

    try:
        call = client.install_app_stream(stream)
        async for response in call:
            if response.HasField("install_loading"):
                if not json_mode:
                    print(f"  {C.DIM}{response.install_loading.loading_message}{C.RESET}")
                continue
            if response.HasField("install_metadata"):
                meta = response.install_metadata
                app_uuid = meta.uuid or app_uuid
                if not json_mode:
                    print(f"  {C.CYAN}{DOT}{C.RESET} {meta.metadata.name}")
                continue
            if response.HasField("install_error"):
                if terminal_result is None:
                    terminal_result = (False, response.install_error.error_message)
                await stream.close()
                continue
            if not response.HasField("install_modal"):
                continue

            modal = response.install_modal
            if modal.HasField("welcome_modal"):
                req = AppInstallRequest()
                req.user_action.next.SetInParent()
                await stream.put(req)
                continue
            if modal.HasField("finish_modal"):
                app_uuid = modal.finish_modal.app_uuid or app_uuid
                if terminal_result is None:
                    terminal_result = (True, app_uuid)
                await stream.close()
                continue
            if mode == "update" and (
                modal.HasField("oauth_modal")
                or modal.HasField("text_fields_modal")
                or modal.HasField("vnc_modal")
            ):
                await _abort_with(UPDATE_REAUTH_MESSAGE)
                continue
            if modal.HasField("vnc_modal"):
                await _abort_with(BROWSER_UNSUPPORTED_MESSAGE)
                continue
            if modal.HasField("text_fields_modal"):
                if no_interactive:
                    await _abort_with("Install requires text input, but --no-interactive was set")
                    continue
                req = AppInstallRequest()
                for key, field in sorted(modal.text_fields_modal.fields.items()):
                    if key in supplied_fields:
                        value = supplied_fields[key]
                    elif field.HasField("default_value"):
                        value = field.default_value
                    elif field.is_password:
                        value = getpass.getpass(f"{field.label or key}: ")
                    else:
                        value = input(f"{field.label or key}: ")
                    req.user_action.text_fields.field_responses[key] = value
                await stream.put(req)
                continue
            if modal.HasField("oauth_modal"):
                if no_interactive:
                    await _abort_with("Install requires OAuth interaction, but --no-interactive was set")
                    continue
                oauth = modal.oauth_modal
                print()
                print(f"{C.BOLD}Open this URL to authorize {oauth.provider}:{C.RESET}")
                print(oauth.auth_url)
                print()
                raw = input("Paste callback URL or authorization code: ")
                code, state = parse_oauth_callback(raw)
                if not code:
                    await _abort_with("OAuth callback did not contain an authorization code")
                    continue
                if not state:
                    state = input("OAuth state: ").strip()
                req = AppInstallRequest()
                req.user_action.oauth.code = code
                req.user_action.oauth.state = state
                await stream.put(req)
                continue
        if terminal_result is not None:
            return terminal_result
        return False, "Install stream ended unexpectedly"
    finally:
        await stream.close()
        if terminal_result is None and call is not None and hasattr(call, "cancel"):
            with contextlib.suppress(Exception):
                call.cancel()


async def cmd_install_store(args, storage: StorageService) -> int:
    json_mode = bool(getattr(args, "json", False))
    try:
        text_fields = _parse_field_args(getattr(args, "field", None))
    except ValueError as exc:
        error(str(exc))
        return 1

    try:
        store_apps = await fetch_store_apps()
        app = find_store_app(store_apps, args.app)
    except Exception as exc:
        error(str(exc))
        return 1

    spinner = _spinner(f"Inspecting {app.name}", enabled=not json_mode)
    spinner.start()
    try:
        await _ensure_cli_supported(app)
        spinner.stop(success=True)
    except Exception as exc:
        spinner.fail(str(exc))
        return 1

    client = None
    spinner = _spinner("Connecting to device", enabled=not json_mode)
    spinner.start()
    try:
        client = await _connect_client(storage)
        if client is None:
            spinner.fail("Could not connect to device")
            return 1
        installed_apps = await client.get_all_apps()
        rows = merge_store_rows([app], installed_apps)
        if rows and rows[0].installed_app is not None:
            spinner.fail(f"{app.name} is already installed")
            print(f"  {C.DIM}Run: truffile update store {app.bundle_id}{C.RESET}")
            return 1
        spinner.stop(success=True)

        ok, detail = await _run_install_stream(
            client=client,
            first_request=_start_install_request(app),
            mode="install",
            text_fields=text_fields,
            no_interactive=bool(getattr(args, "no_interactive", False)),
            json_mode=json_mode,
        )
        if ok:
            if json_mode:
                _json_print(_app_result(app, "installed", app_uuid=detail))
            else:
                success(f"Installed {app.name}")
                if detail:
                    print(f"  {C.DIM}app uuid: {detail}{C.RESET}")
            return 0
        error(detail)
        return 1
    except Exception as exc:
        spinner.fail(str(exc))
        return 1
    finally:
        if client:
            await client.close()


async def _update_one(client: TruffleClient, app: StoreApp, installed_app: App, *, json_mode: bool) -> tuple[bool, str]:
    await _ensure_cli_supported(app)
    ok, detail = await _run_install_stream(
        client=client,
        first_request=_start_update_request(app, installed_app.uuid),
        mode="update",
        json_mode=json_mode,
        no_interactive=True,
    )
    return ok, detail


async def cmd_update_store(args, storage: StorageService) -> int:
    json_mode = bool(getattr(args, "json", False))
    try:
        store_apps = await fetch_store_apps()
    except Exception as exc:
        error(f"Failed to fetch app store manifest: {exc}")
        return 1

    client = None
    spinner = _spinner("Connecting to device", enabled=not json_mode)
    spinner.start()
    try:
        client = await _connect_client(storage)
        if client is None:
            spinner.fail("Could not connect to device")
            return 1
        installed_apps = await client.get_all_apps()
        spinner.stop(success=True)

        rows = merge_store_rows(store_apps, installed_apps)
        if getattr(args, "all", False):
            targets = [row for row in rows if row.update_available and row.installed_app is not None]
            if not targets:
                if json_mode:
                    _json_print({"status": "up_to_date"})
                else:
                    success("All store apps are up to date")
                return 0
        else:
            try:
                app = find_store_app(store_apps, args.app)
            except Exception as exc:
                error(str(exc))
                return 1
            row = merge_store_rows([app], installed_apps)[0]
            if row.installed_app is None:
                error(f"{app.name} is not installed")
                return 1
            if not row.update_available:
                if json_mode:
                    _json_print(_app_result(app, "up_to_date", app_uuid=row.installed_app.uuid))
                else:
                    success(f"{app.name} is already up to date")
                return 0
            targets = [row]

        results = []
        failed = False
        for row in targets:
            app = row.app
            assert row.installed_app is not None
            spinner = _spinner(f"Updating {app.name}", enabled=not json_mode)
            spinner.start()
            try:
                ok, detail = await _update_one(client, app, row.installed_app, json_mode=json_mode)
                if ok:
                    spinner.stop(success=True)
                    results.append(_app_result(app, "updated", app_uuid=detail))
                else:
                    spinner.fail(detail)
                    failed = True
                    results.append(_app_result(app, "failed", error_message=detail))
            except Exception as exc:
                spinner.fail(str(exc))
                failed = True
                results.append(_app_result(app, "failed", error_message=str(exc)))

        if json_mode:
            if getattr(args, "all", False):
                _json_print(results)
            else:
                _json_print(results[0] if results else {"status": "up_to_date"})
        return 1 if failed else 0
    except Exception as exc:
        spinner.fail(str(exc))
        return 1
    finally:
        if client:
            await client.close()
