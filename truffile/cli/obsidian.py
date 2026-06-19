from __future__ import annotations

import json
import os
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import httpx
import yaml

from truffile.client import TruffleClient
from truffile.storage import StorageService, StoredObsidianBridge

from .connect import _resolve_connected_device
from .obsidian_bridge import (
    ObsidianBridgeConfig,
    build_server,
    ensure_vault_access,
    normalize_vault_path,
)
from .ui import C, Spinner, error, info, success, warn


DEFAULT_OBSIDIAN_PORT = 27125
LOG_FILE_NAME = "obsidian-bridge.log"
OBSIDIAN_APP_RAW_BASE_URL = "https://raw.githubusercontent.com/deepshard/truffile/main/truffile/app-store/obsidian"
OBSIDIAN_APP_FILES = (
    "truffile.yaml",
    "bridge_client.py",
    "obsidian_foreground.py",
    "icon.png",
)


def _default_obsidian_app_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "app-store" / "obsidian"


def _step_spinner(step: str) -> Spinner:
    return Spinner(f"{C.DIM}{step}{C.RESET}")


def _fetch_bytes(url: str, *, timeout: float = 15.0) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "truffile-obsidian-deploy/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _stage_obsidian_app(temp_root: Path, source_arg: str | None) -> Path:
    temp_app_dir = temp_root / "obsidian"
    if not source_arg or source_arg == "obsidian":
        temp_app_dir.mkdir(parents=True, exist_ok=True)
        for filename in OBSIDIAN_APP_FILES:
            url = f"{OBSIDIAN_APP_RAW_BASE_URL}/{filename}"
            try:
                payload = _fetch_bytes(url)
            except Exception as exc:
                raise RuntimeError(f"Failed to fetch Obsidian app file from {url}: {exc}") from exc
            (temp_app_dir / filename).write_bytes(payload)
        return temp_app_dir

    source_app_dir = Path(source_arg).resolve()
    if not source_app_dir.exists():
        raise RuntimeError(f"Obsidian app directory not found: {source_app_dir}")
    shutil.copytree(source_app_dir, temp_app_dir)
    return temp_app_dir


def _configure_staged_obsidian_manifest(manifest_path: Path, config: ObsidianBridgeConfig) -> None:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    env = (
        manifest.setdefault("metadata", {})
        .setdefault("foreground", {})
        .setdefault("process", {})
        .setdefault("environment", {})
    )
    env["OBSIDIAN_BRIDGE_BASE_URL"] = _device_bridge_url(config)
    env["OBSIDIAN_BRIDGE_TOKEN"] = config.token

    # The packaged Obsidian app needs a text step so users can provide bridge
    # credentials. The bespoke `truffile obsidian deploy` flow has already
    # started/probed the bridge and injects those credentials here, so keeping
    # that step would create a redundant prompt.
    steps = manifest.get("steps")
    if isinstance(steps, list):
        manifest["steps"] = [
            step
            for step in steps
            if not (
                isinstance(step, dict)
                and step.get("type") == "text"
                and any(
                    isinstance(field, dict)
                    and field.get("env") in {"OBSIDIAN_BRIDGE_BASE_URL", "OBSIDIAN_BRIDGE_TOKEN"}
                    for field in step.get("fields", [])
                )
            )
        ]

    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def _best_effort_advertise_host() -> str:
    probe_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe_socket.connect(("8.8.8.8", 80))
        ip = probe_socket.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        probe_socket.close()

    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass

    raise RuntimeError("Could not determine a non-loopback host address; pass --advertise-host")


def _pick_vault_path() -> str:
    if sys.platform == "darwin":
        script = 'POSIX path of (choose folder with prompt "Select your Obsidian vault")'
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(stderr or "Vault selection was cancelled")
        picked = (result.stdout or "").strip()
        if not picked:
            raise RuntimeError("Vault selection was cancelled")
        return picked
    raise RuntimeError("Vault picker is currently supported on macOS only")


def _require_bridge(storage: StorageService) -> StoredObsidianBridge:
    bridge = storage.get_obsidian_bridge()
    if bridge is None:
        raise RuntimeError("No Obsidian vault is configured yet")
    return bridge


def _bridge_config(bridge: StoredObsidianBridge) -> ObsidianBridgeConfig:
    vault_path = normalize_vault_path(bridge.vault_path)
    ensure_vault_access(vault_path)
    return ObsidianBridgeConfig(
        vault_path=vault_path,
        token=bridge.token,
        bind_host=bridge.bind_host,
        advertise_host=bridge.advertise_host,
        port=bridge.port,
    )


def _obsidian_log_path(storage: StorageService) -> Path:
    return storage.storage_dir / LOG_FILE_NAME


def _tail_log(storage: StorageService, lines: int = 20) -> str:
    log_path = _obsidian_log_path(storage)
    if not log_path.exists():
        return ""
    data = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(data[-max(1, lines):]).strip()


def _local_bridge_url(config: ObsidianBridgeConfig) -> str:
    return f"http://127.0.0.1:{config.port}"


def _device_bridge_url(config: ObsidianBridgeConfig) -> str:
    return f"http://{config.advertise_host}:{config.port}"


def _probe_bridge(url: str, token: str, *, timeout: float = 3.0) -> dict[str, object]:
    req = urllib.request.Request(
        url.rstrip("/") + "/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
        return {"status": response.status, "body": body}


def _probe_bridge_error(url: str, token: str, *, timeout: float = 3.0) -> str | None:
    try:
        _probe_bridge(url, token, timeout=timeout)
        return None
    except Exception as exc:
        return repr(exc)


def _bridge_healthy(config: ObsidianBridgeConfig) -> bool:
    try:
        result = _probe_bridge(_local_bridge_url(config), config.token)
        return int(result["status"]) == 200
    except Exception:
        return False


def _truffile_command(*args: str) -> list[str]:
    return [
        sys.executable,
        "-c",
        (
            "import sys; "
            "from truffile.cli import main; "
            "sys.argv = ['truffile', *sys.argv[1:]]; "
            "raise SystemExit(main())"
        ),
        *args,
    ]


def _screen_session_name_for_port(port: int) -> str:
    return f"truffile-obsidian-{port}"


def _screen_session_name(config: ObsidianBridgeConfig) -> str:
    return _screen_session_name_for_port(config.port)


def _screen_binary() -> str | None:
    return shutil.which("screen")


def _require_screen() -> str:
    screen_bin = _screen_binary()
    if screen_bin:
        return screen_bin
    if sys.platform == "darwin":
        raise RuntimeError("`screen` is required for the Obsidian bridge manager. Install it with `brew install screen`.")
    if os.name == "nt":
        raise RuntimeError("`screen` is required for the Obsidian bridge manager, but it was not found. Install GNU screen in your shell environment and retry.")
    raise RuntimeError("`screen` is required for the Obsidian bridge manager. Install it with your package manager and retry.")


def _screen_session_running(config: ObsidianBridgeConfig) -> bool:
    screen_bin = _screen_binary()
    if not screen_bin:
        return False
    result = subprocess.run(
        [screen_bin, "-ls"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        return False
    return _screen_session_name(config) in result.stdout


def _list_managed_bridge_processes() -> list[tuple[int, str]]:
    if os.name == "nt":
        return []
    result = subprocess.run(
        ["ps", "-axo", "pid=,command="],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    managed: list[tuple[int, str]] = []
    current_pid = os.getpid()
    for line in result.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            pid_text, command = text.split(None, 1)
        except ValueError:
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid == current_pid:
            continue
        if "obsidian serve" not in command:
            continue
        if "truffile.cli" not in command and "truffile obsidian serve" not in command:
            continue
        managed.append((pid, command))
    return managed


def _terminate_process(pid: int) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return True

    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.1)

    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return True
    return True


def _start_bridge_background(storage: StorageService, config: ObsidianBridgeConfig) -> None:
    _stop_bridge_background(storage)

    storage.storage_dir.mkdir(parents=True, exist_ok=True)
    screen_bin = _require_screen()
    log_path = _obsidian_log_path(storage)
    log_path.write_text("", encoding="utf-8")
    command = shlex.join(_truffile_command("obsidian", "serve"))
    shell_command = f"exec {command} >> {shlex.quote(str(log_path))} 2>&1"
    result = subprocess.run(
        [
            screen_bin,
            "-dmS",
            _screen_session_name(config),
            "/bin/sh",
            "-lc",
            shell_command,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(Path.cwd()),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        message = "Failed to launch the Obsidian bridge screen session."
        if detail:
            message += f" {detail}"
        raise RuntimeError(message)

    deadline = time.time() + 8.0
    last_probe_error: str | None = None
    while time.time() < deadline:
        probe_error = _probe_bridge_error(_local_bridge_url(config), config.token, timeout=1.0)
        if probe_error is None:
            return
        last_probe_error = probe_error
        if not _screen_session_running(config):
            break
        time.sleep(0.25)

    log_tail = _tail_log(storage)
    if not _screen_session_running(config):
        if "Address already in use" in log_tail:
            try:
                result = _probe_bridge(_local_bridge_url(config), config.token, timeout=1.0)
                if int(result["status"]) == 200:
                    return
            except Exception:
                pass

        message = (
            "Failed to start the Obsidian bridge in the background. "
            "The screen session exited early. Check logs with `truffile obsidian logs`."
        )
        if "Address already in use" in log_tail:
            message = (
                f"Port {config.port} is already in use and the existing process did not match the saved bridge configuration. "
                "Stop the existing process or choose a different port with "
                "`truffile deploy obsidian --port <port> --obsidian-reconfigure`."
            )
        if last_probe_error:
            message += f"\n\nLast local health-check error:\n{last_probe_error}"
        if log_tail:
            message += f"\n\nRecent log output:\n{log_tail}"
        raise RuntimeError(message)

    if "Obsidian bridge listening" in log_tail:
        return

    message = "Failed to start the Obsidian bridge in the background. Check logs with `truffile obsidian logs`."
    if last_probe_error:
        message += f"\n\nLast local health-check error:\n{last_probe_error}"
    if log_tail:
        message += f"\n\nRecent log output:\n{log_tail}"
    raise RuntimeError(message)


def _stop_bridge_background(storage: StorageService) -> None:
    bridge = storage.get_obsidian_bridge()
    if bridge is None:
        return
    session_name = _screen_session_name_for_port(bridge.port)
    if not _screen_binary():
        return
    result = subprocess.run(
        [_require_screen(), "-ls"],
        check=False,
        capture_output=True,
        text=True,
    )
    if session_name not in result.stdout:
        return
    subprocess.run(
        [_require_screen(), "-S", session_name, "-X", "quit"],
        check=False,
        capture_output=True,
        text=True,
    )
    deadline = time.time() + 5.0
    while time.time() < deadline:
        result = subprocess.run(
            [_require_screen(), "-ls"],
            check=False,
            capture_output=True,
            text=True,
        )
        if session_name not in result.stdout:
            break
        time.sleep(0.1)

    for pid, _command in _list_managed_bridge_processes():
        _terminate_process(pid)


def _ensure_bridge_running(storage: StorageService, config: ObsidianBridgeConfig) -> None:
    _start_bridge_background(storage, config)


def _collect_bridge_config(
    storage: StorageService,
    *,
    raw_vault: str | None = None,
    pick_vault: bool = False,
    advertise_host: str | None = None,
    bind_host: str | None = None,
    port: int | None = None,
    token: str | None = None,
    force_reconfigure: bool = False,
) -> ObsidianBridgeConfig:
    existing = storage.get_obsidian_bridge()
    has_overrides = (
        force_reconfigure
        or raw_vault is not None
        or pick_vault
        or advertise_host is not None
        or bind_host is not None
        or port is not None
        or token is not None
    )
    if existing is not None and not has_overrides:
        return _bridge_config(existing)

    selected_vault = raw_vault or (existing.vault_path if existing is not None else None)
    if pick_vault or not selected_vault:
        selected_vault = _pick_vault_path()

    vault_path = normalize_vault_path(selected_vault)
    ensure_vault_access(vault_path)

    bridge = StoredObsidianBridge(
        vault_path=str(vault_path),
        token=token or (existing.token if existing is not None else secrets.token_urlsafe(24)),
        advertise_host=advertise_host or (existing.advertise_host if existing is not None else _best_effort_advertise_host()),
        port=int(port or (existing.port if existing is not None else DEFAULT_OBSIDIAN_PORT)),
        bind_host=bind_host or (existing.bind_host if existing is not None else "0.0.0.0"),
    )
    storage.set_obsidian_bridge(bridge)
    return _bridge_config(bridge)


def cmd_obsidian_attach(args, storage: StorageService) -> int:
    try:
        config = _collect_bridge_config(
            storage,
            raw_vault=getattr(args, "vault", None),
            pick_vault=bool(getattr(args, "pick_vault", False) or not getattr(args, "vault", None)),
            advertise_host=getattr(args, "advertise_host", None),
            bind_host=getattr(args, "bind_host", None),
            port=getattr(args, "port", None),
            token=getattr(args, "token", None),
            force_reconfigure=True,
        )
    except Exception as exc:
        error(str(exc))
        return 1

    print()
    success("Saved Obsidian vault configuration")
    print(f"  {C.DIM}vault:{C.RESET}          {config.vault_path}")
    print(f"  {C.DIM}bind host:{C.RESET}      {config.bind_host}")
    print(f"  {C.DIM}advertise host:{C.RESET} {config.advertise_host}")
    print(f"  {C.DIM}port:{C.RESET}           {config.port}")
    print(f"  {C.DIM}token:{C.RESET}          {config.token[:8]}...")
    print()
    print(f"  {C.DIM}Next:{C.RESET}")
    print(f"    {C.CYAN}truffile deploy obsidian{C.RESET}")
    print(f"    {C.CYAN}truffile obsidian status{C.RESET}")
    return 0


def cmd_obsidian_status(args, storage: StorageService) -> int:
    bridge = storage.get_obsidian_bridge()
    if bridge is None:
        error("No Obsidian vault is configured")
        print(f"  {C.DIM}Run: truffile deploy obsidian{C.RESET}")
        return 1

    try:
        config = _bridge_config(bridge)
        access_note = "ok"
    except Exception as exc:
        config = None
        access_note = str(exc)

    running = False
    local_health = "unreachable"
    if config is not None:
        running = _screen_session_running(config)
        try:
            result = _probe_bridge(_local_bridge_url(config), config.token)
            local_health = f"ok ({result['status']})"
        except Exception as exc:
            local_health = f"unreachable ({exc!r})"

    print()
    print(f"{C.BOLD}Obsidian Bridge{C.RESET}")
    print(f"  {C.DIM}vault:{C.RESET}          {bridge.vault_path}")
    print(f"  {C.DIM}bind host:{C.RESET}      {bridge.bind_host}")
    print(f"  {C.DIM}advertise host:{C.RESET} {bridge.advertise_host}")
    print(f"  {C.DIM}port:{C.RESET}           {bridge.port}")
    print(f"  {C.DIM}token:{C.RESET}          {bridge.token[:8]}...")
    print(f"  {C.DIM}vault access:{C.RESET}   {access_note}")
    print(f"  {C.DIM}screen session:{C.RESET} {_screen_session_name_for_port(bridge.port)}")
    print(f"  {C.DIM}running:{C.RESET}        {'yes' if running else 'no'}")
    print(f"  {C.DIM}local health:{C.RESET}   {local_health}")
    print(f"  {C.DIM}logs:{C.RESET}           {_obsidian_log_path(storage)}")
    print()
    return 0


def cmd_obsidian_restart(args, storage: StorageService) -> int:
    spinner = _step_spinner("Restarting local Obsidian bridge")
    spinner.start()
    try:
        config = _bridge_config(_require_bridge(storage))
        _stop_bridge_background(storage)
        _start_bridge_background(storage, config)
        spinner.stop(success=True)
    except Exception as exc:
        spinner.fail("Restarting local Obsidian bridge")
        error(str(exc))
        return 1

    print()
    success("Restarted the Obsidian bridge")
    print(f"  {C.DIM}url:{C.RESET} {_device_bridge_url(config)}")
    print()
    return 0


def cmd_obsidian_logs(args, storage: StorageService) -> int:
    log_path = _obsidian_log_path(storage)
    if not log_path.exists():
        error(f"No log file found at {log_path}")
        return 1

    lines = max(1, int(getattr(args, "lines", 40)))
    data = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    print()
    print("\n".join(data[-lines:]))
    print()
    return 0


async def _probe_bridge_from_device(storage: StorageService, config: ObsidianBridgeConfig) -> tuple[bool, list[str]]:
    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return False, ["No connected device could be resolved"]

    token = storage.get_token(device)
    if not token:
        return False, [f"No token stored for {device}"]

    client = TruffleClient(f"{ip}:80", token=token, app_id=storage.app_id_for_device(device))
    try:
        await client.connect()
        await client.start_build()
        probe_script = f"""python - <<'PY'
import json
import urllib.request
import sys

url = {json.dumps(_device_bridge_url(config) + "/health")}
headers = {json.dumps({"Authorization": f"Bearer {config.token}"})}
req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        print(json.dumps({{"status": resp.status, "body": body}}))
except Exception as exc:
    print(json.dumps({{"error": repr(exc)}}))
    sys.exit(2)
PY"""
        result = await client.exec(probe_script, cwd="/")
        return result.exit_code == 0, result.output
    finally:
        try:
            await client.discard()
        except Exception:
            pass
        await client.close()


async def cmd_obsidian_test(args, storage: StorageService) -> int:
    try:
        config = _bridge_config(_require_bridge(storage))
    except Exception as exc:
        error(str(exc))
        return 1

    local_ok = False
    print()
    info("Testing local bridge access")
    try:
        result = _probe_bridge(_local_bridge_url(config), config.token)
        async with httpx.AsyncClient(
            timeout=5.0,
            headers={"Authorization": f"Bearer {config.token}"},
            trust_env=False,
        ) as client:
            files = await client.get(_local_bridge_url(config) + "/files", params={"directory": "/"})
            files.raise_for_status()
            count = len(files.json().get("files", []))
        success(f"Local bridge OK at {_local_bridge_url(config)}")
        print(f"  {C.DIM}{result['body']}{C.RESET}")
        print(f"  {C.DIM}root entries:{C.RESET} {count}")
        local_ok = True
    except Exception as exc:
        error(f"Local bridge probe failed: {exc}")

    if getattr(args, "local_only", False):
        print()
        return 0 if local_ok else 1

    print()
    info("Testing bridge access from the device")
    ok_from_device, lines = await _probe_bridge_from_device(storage, config)
    if ok_from_device:
        success("Device can reach the bridge")
    else:
        error("Device could not reach the bridge")
    for line in lines[-3:]:
        print(f"  {C.DIM}{line}{C.RESET}")
    if ok_from_device and not local_ok:
        print()
        warn("The bridge is reachable from the device, but the local localhost probe timed out.")
        print(f"  {C.DIM}This does not block the Obsidian app on Truffle from working; it only affects the host-side self-check.{C.RESET}")
    print()
    return 0 if ok_from_device else 1


def cmd_obsidian_serve(args, storage: StorageService) -> int:
    try:
        config = _bridge_config(_require_bridge(storage))
    except Exception as exc:
        error(str(exc))
        return 1

    server = build_server(config)
    print()
    success("Obsidian bridge listening")
    print(f"  {C.DIM}vault:{C.RESET}      {config.vault_path}")
    print(f"  {C.DIM}local URL:{C.RESET}  {_local_bridge_url(config)}")
    print(f"  {C.DIM}device URL:{C.RESET} {_device_bridge_url(config)}")
    print(f"  {C.DIM}auth:{C.RESET}       bearer token configured")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        info("Stopping Obsidian bridge")
    finally:
        server.server_close()
    return 0


async def cmd_obsidian_deploy(args, storage: StorageService) -> int:
    bridge_spinner = _step_spinner("Preparing local Obsidian bridge")
    bridge_spinner.start()
    try:
        config = _collect_bridge_config(
            storage,
            raw_vault=getattr(args, "vault", None),
            pick_vault=bool(getattr(args, "pick_vault", False)),
            advertise_host=getattr(args, "advertise_host", None),
            bind_host=getattr(args, "bind_host", None),
            port=getattr(args, "port", None),
            token=getattr(args, "token", None),
            force_reconfigure=bool(getattr(args, "obsidian_reconfigure", False)),
        )
        if not bool(getattr(args, "dry_run", False)):
            _ensure_bridge_running(storage, config)
        bridge_spinner.stop(success=True)
    except Exception as exc:
        bridge_spinner.fail("Preparing local Obsidian bridge")
        error(str(exc))
        return 1

    if not bool(getattr(args, "dry_run", False)):
        device_spinner = _step_spinner("Checking bridge access from the device")
        device_spinner.start()
        ok_from_device, lines = await _probe_bridge_from_device(storage, config)
        if not ok_from_device:
            device_spinner.fail("Checking bridge access from the device")
            error("The device cannot reach the Obsidian bridge")
            for line in lines[-3:]:
                print(f"  {C.DIM}{line}{C.RESET}")
            print(f"  {C.DIM}Try `truffile obsidian status`, `truffile obsidian restart`, or `truffile obsidian logs`.{C.RESET}")
            return 1
        device_spinner.stop(success=True)

    with tempfile.TemporaryDirectory(prefix="truffile-obsidian-app-") as tmp_dir:
        stage_spinner = _step_spinner("Staging Obsidian app source")
        stage_spinner.start()
        try:
            temp_app_dir = _stage_obsidian_app(Path(tmp_dir), getattr(args, "path", None))
            stage_spinner.stop(success=True)
        except Exception as exc:
            stage_spinner.fail("Staging Obsidian app source")
            error(str(exc))
            return 1

        manifest_path = temp_app_dir / "truffile.yaml"
        _configure_staged_obsidian_manifest(manifest_path, config)

        deploy_args = SimpleNamespace(
            path=str(temp_app_dir),
            shell=bool(getattr(args, "shell", False)),
            interactive=bool(getattr(args, "interactive", False)),
            dry_run=bool(getattr(args, "dry_run", False)),
            no_finalize=bool(getattr(args, "no_finalize", False)),
        )
        from .deploy import cmd_deploy
        return await cmd_deploy(deploy_args, storage)
