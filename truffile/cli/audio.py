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
from pathlib import Path
from types import SimpleNamespace

import httpx
import yaml

from truffile.storage import StorageService, StoredAudioBridge

from .audio_bridge import AudioBridgeConfig, build_server, normalize_cache_path
from .ui import C, Spinner, error, info, success


DEFAULT_AUDIO_PORT = 27126
LOG_FILE_NAME = "audio-bridge.log"


def _step_spinner(step: str) -> Spinner:
    return Spinner(f"{C.DIM}{step}{C.RESET}")


def _default_cache_path(storage: StorageService) -> Path:
    return storage.storage_dir / "audio"


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


def _require_bridge(storage: StorageService) -> StoredAudioBridge:
    bridge = storage.get_audio_bridge()
    if bridge is None:
        raise RuntimeError("No local audio bridge is configured yet")
    return bridge


def _bridge_config(bridge: StoredAudioBridge) -> AudioBridgeConfig:
    return AudioBridgeConfig(
        cache_path=normalize_cache_path(bridge.cache_path),
        token=bridge.token,
        bind_host=bridge.bind_host,
        advertise_host=bridge.advertise_host,
        port=bridge.port,
    )


def _audio_log_path(storage: StorageService) -> Path:
    return storage.storage_dir / LOG_FILE_NAME


def _tail_log(storage: StorageService, lines: int = 20) -> str:
    log_path = _audio_log_path(storage)
    if not log_path.exists():
        return ""
    data = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(data[-max(1, lines):]).strip()


def _local_bridge_url(config: AudioBridgeConfig) -> str:
    return f"http://127.0.0.1:{config.port}"


def _device_bridge_url(config: AudioBridgeConfig) -> str:
    return f"http://{config.advertise_host}:{config.port}"


def _probe_bridge(url: str, token: str, *, timeout: float = 3.0) -> dict[str, object]:
    with httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {token}"}, trust_env=False) as client:
        resp = client.get(url.rstrip("/") + "/health")
        return {"status": resp.status_code, "body": resp.text}


def _probe_bridge_error(url: str, token: str, *, timeout: float = 3.0) -> str | None:
    try:
        result = _probe_bridge(url, token, timeout=timeout)
        if int(result["status"]) == 200:
            return None
        return f"HTTP {result['status']}: {result['body']}"
    except Exception as exc:
        return repr(exc)


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
    return f"truffile-audio-{port}"


def _screen_session_name(config: AudioBridgeConfig) -> str:
    return _screen_session_name_for_port(config.port)


def _screen_binary() -> str | None:
    return shutil.which("screen")


def _require_screen() -> str:
    screen_bin = _screen_binary()
    if screen_bin:
        return screen_bin
    raise RuntimeError("`screen` is required for the audio bridge manager. Install it with your package manager and retry.")


def _screen_session_running(config: AudioBridgeConfig) -> bool:
    screen_bin = _screen_binary()
    if not screen_bin:
        return False
    result = subprocess.run([screen_bin, "-ls"], check=False, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        return False
    return _screen_session_name(config) in result.stdout


def _list_managed_bridge_processes() -> list[tuple[int, str]]:
    if os.name == "nt":
        return []
    result = subprocess.run(["ps", "-axo", "pid=,command="], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return []
    current_pid = os.getpid()
    managed: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            pid_text, command = text.split(None, 1)
            pid = int(pid_text)
        except ValueError:
            continue
        if pid == current_pid:
            continue
        if "audio serve" in command and ("truffile.cli" in command or "truffile audio serve" in command):
            managed.append((pid, command))
    return managed


def _terminate_process(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


def _stop_bridge_background(storage: StorageService) -> None:
    bridge = storage.get_audio_bridge()
    if bridge is None or not _screen_binary():
        return
    session_name = _screen_session_name_for_port(bridge.port)
    result = subprocess.run([_require_screen(), "-ls"], check=False, capture_output=True, text=True)
    if session_name in result.stdout:
        subprocess.run([_require_screen(), "-S", session_name, "-X", "quit"], check=False, capture_output=True, text=True)
    for pid, _command in _list_managed_bridge_processes():
        _terminate_process(pid)


def _start_bridge_background(storage: StorageService, config: AudioBridgeConfig) -> None:
    _stop_bridge_background(storage)
    storage.storage_dir.mkdir(parents=True, exist_ok=True)
    screen_bin = _require_screen()
    log_path = _audio_log_path(storage)
    log_path.write_text("", encoding="utf-8")
    command = shlex.join(_truffile_command("audio", "serve"))
    shell_command = f"exec {command} >> {shlex.quote(str(log_path))} 2>&1"
    result = subprocess.run(
        [screen_bin, "-dmS", _screen_session_name(config), "/bin/sh", "-lc", shell_command],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(Path.cwd()),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Failed to launch the audio bridge screen session. {detail}".strip())

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

    message = "Failed to start the audio bridge in the background. Check logs with `truffile audio logs`."
    if last_probe_error:
        message += f"\n\nLast local health-check error:\n{last_probe_error}"
    log_tail = _tail_log(storage)
    if log_tail:
        message += f"\n\nRecent log output:\n{log_tail}"
    raise RuntimeError(message)


def _collect_bridge_config(
    storage: StorageService,
    *,
    raw_cache: str | None = None,
    advertise_host: str | None = None,
    bind_host: str | None = None,
    port: int | None = None,
    token: str | None = None,
    force_reconfigure: bool = False,
) -> AudioBridgeConfig:
    existing = storage.get_audio_bridge()
    has_overrides = (
        force_reconfigure
        or raw_cache is not None
        or advertise_host is not None
        or bind_host is not None
        or port is not None
        or token is not None
    )
    if existing is not None and not has_overrides:
        return _bridge_config(existing)

    cache_path = normalize_cache_path(raw_cache or (existing.cache_path if existing is not None else str(_default_cache_path(storage))))
    bridge = StoredAudioBridge(
        cache_path=str(cache_path),
        token=token or (existing.token if existing is not None else secrets.token_urlsafe(24)),
        advertise_host=advertise_host or (existing.advertise_host if existing is not None else _best_effort_advertise_host()),
        port=int(port or (existing.port if existing is not None else DEFAULT_AUDIO_PORT)),
        bind_host=bind_host or (existing.bind_host if existing is not None else "0.0.0.0"),
    )
    storage.set_audio_bridge(bridge)
    return _bridge_config(bridge)


def cmd_audio_attach(args, storage: StorageService) -> int:
    try:
        config = _collect_bridge_config(
            storage,
            raw_cache=getattr(args, "cache", None),
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
    success("Saved local audio bridge configuration")
    print(f"  {C.DIM}cache:{C.RESET}          {config.cache_path}")
    print(f"  {C.DIM}bind host:{C.RESET}      {config.bind_host}")
    print(f"  {C.DIM}advertise host:{C.RESET} {config.advertise_host}")
    print(f"  {C.DIM}port:{C.RESET}           {config.port}")
    print(f"  {C.DIM}token:{C.RESET}          {config.token[:8]}...")
    print()
    return 0


def cmd_audio_status(args, storage: StorageService) -> int:
    bridge = storage.get_audio_bridge()
    if bridge is None:
        error("No local audio bridge is configured")
        print(f"  {C.DIM}Run: truffile audio attach{C.RESET}")
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
    print(f"{C.BOLD}Audio Bridge{C.RESET}")
    print(f"  {C.DIM}cache:{C.RESET}          {bridge.cache_path}")
    print(f"  {C.DIM}bind host:{C.RESET}      {bridge.bind_host}")
    print(f"  {C.DIM}advertise host:{C.RESET} {bridge.advertise_host}")
    print(f"  {C.DIM}port:{C.RESET}           {bridge.port}")
    print(f"  {C.DIM}token:{C.RESET}          {bridge.token[:8]}...")
    print(f"  {C.DIM}cache access:{C.RESET}   {access_note}")
    print(f"  {C.DIM}screen session:{C.RESET} {_screen_session_name_for_port(bridge.port)}")
    print(f"  {C.DIM}running:{C.RESET}        {'yes' if running else 'no'}")
    print(f"  {C.DIM}local health:{C.RESET}   {local_health}")
    print(f"  {C.DIM}logs:{C.RESET}           {_audio_log_path(storage)}")
    print()
    return 0


def cmd_audio_restart(args, storage: StorageService) -> int:
    spinner = _step_spinner("Restarting local audio bridge")
    spinner.start()
    try:
        config = _bridge_config(_require_bridge(storage))
        _stop_bridge_background(storage)
        _start_bridge_background(storage, config)
        spinner.stop(success=True)
    except Exception as exc:
        spinner.fail("Restarting local audio bridge")
        error(str(exc))
        return 1

    print()
    success("Restarted the local audio bridge")
    print(f"  {C.DIM}url:{C.RESET} {_device_bridge_url(config)}")
    print()
    return 0


def cmd_audio_logs(args, storage: StorageService) -> int:
    log_path = _audio_log_path(storage)
    if not log_path.exists():
        error(f"No log file found at {log_path}")
        return 1
    lines = max(1, int(getattr(args, "lines", 40)))
    data = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    print()
    print("\n".join(data[-lines:]))
    print()
    return 0


async def _probe_bridge_from_device(storage: StorageService, config: AudioBridgeConfig) -> tuple[bool, list[str]]:
    from truffile.client import TruffleClient
    from .connect import _resolve_connected_device

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


async def cmd_audio_test(args, storage: StorageService) -> int:
    try:
        config = _bridge_config(_require_bridge(storage))
    except Exception as exc:
        error(str(exc))
        return 1

    local_ok = False
    print()
    info("Testing local audio bridge access")
    try:
        result = _probe_bridge(_local_bridge_url(config), config.token)
        local_ok = int(result["status"]) == 200
        success(f"Local audio bridge OK at {_local_bridge_url(config)}")
        print(f"  {C.DIM}{result['body']}{C.RESET}")
    except Exception as exc:
        error(f"Local audio bridge probe failed: {exc}")

    if getattr(args, "local_only", False):
        print()
        return 0 if local_ok else 1

    print()
    info("Testing audio bridge access from the device")
    ok_from_device, lines = await _probe_bridge_from_device(storage, config)
    if ok_from_device:
        success("Device can reach the audio bridge")
    else:
        error("Device could not reach the audio bridge")
    for line in lines[-3:]:
        print(f"  {C.DIM}{line}{C.RESET}")
    print()
    return 0 if ok_from_device else 1


def cmd_audio_serve(args, storage: StorageService) -> int:
    try:
        config = _bridge_config(_require_bridge(storage))
    except Exception as exc:
        error(str(exc))
        return 1

    server = build_server(config)
    print()
    success("Audio bridge listening")
    print(f"  {C.DIM}cache:{C.RESET}      {config.cache_path}")
    print(f"  {C.DIM}local URL:{C.RESET}  {_local_bridge_url(config)}")
    print(f"  {C.DIM}device URL:{C.RESET} {_device_bridge_url(config)}")
    print(f"  {C.DIM}auth:{C.RESET}       bearer token configured")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        info("Stopping audio bridge")
    finally:
        server.server_close()
    return 0


async def cmd_audio_deploy(args, storage: StorageService) -> int:
    bridge_spinner = _step_spinner("Preparing local audio bridge")
    bridge_spinner.start()
    try:
        config = _collect_bridge_config(
            storage,
            raw_cache=getattr(args, "cache", None),
            advertise_host=getattr(args, "advertise_host", None),
            bind_host=getattr(args, "bind_host", None),
            port=getattr(args, "port", None),
            token=getattr(args, "token", None),
            force_reconfigure=bool(getattr(args, "audio_reconfigure", False)),
        )
        if not bool(getattr(args, "dry_run", False)):
            _start_bridge_background(storage, config)
        bridge_spinner.stop(success=True)
    except Exception as exc:
        bridge_spinner.fail("Preparing local audio bridge")
        error(str(exc))
        return 1

    if not bool(getattr(args, "dry_run", False)):
        device_spinner = _step_spinner("Checking audio bridge access from the device")
        device_spinner.start()
        ok_from_device, lines = await _probe_bridge_from_device(storage, config)
        if not ok_from_device:
            device_spinner.fail("Checking audio bridge access from the device")
            error("The device cannot reach the local audio bridge")
            for line in lines[-3:]:
                print(f"  {C.DIM}{line}{C.RESET}")
            return 1
        device_spinner.stop(success=True)

    source_app_dir = Path(getattr(args, "path", None) or ".").resolve()
    with tempfile.TemporaryDirectory(prefix="truffile-audio-app-") as tmp_dir:
        temp_app_dir = Path(tmp_dir) / source_app_dir.name
        shutil.copytree(source_app_dir, temp_app_dir)

        manifest_path = temp_app_dir / "truffile.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        env = (
            manifest.setdefault("metadata", {})
            .setdefault("foreground", {})
            .setdefault("process", {})
            .setdefault("environment", {})
        )
        env["TRUFFILE_AUDIO_BRIDGE_BASE_URL"] = _device_bridge_url(config)
        env["TRUFFILE_AUDIO_BRIDGE_TOKEN"] = config.token
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

        deploy_args = SimpleNamespace(
            path=str(temp_app_dir),
            shell=bool(getattr(args, "shell", False)),
            interactive=bool(getattr(args, "interactive", False)),
            dry_run=bool(getattr(args, "dry_run", False)),
            no_finalize=bool(getattr(args, "no_finalize", False)),
        )
        from .deploy import cmd_deploy
        return await cmd_deploy(deploy_args, storage)
