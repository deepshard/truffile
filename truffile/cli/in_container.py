"""In-container connection mode for the truffile CLI.

When `truffile` is invoked from inside a Truffle app container, the CNI bridge
isolates it from the LAN and the normal mDNS discovery flow finds nothing.
But the container is already holding a full user session token on a gRPC
channel that reaches the host firmware. This module detects that context and
exposes the env-provided gRPC address + session token so the rest of the CLI
can short-circuit discovery and talk to the host directly.

Detection criterion: APP_ID + APP_SESSION_TOKEN + GRPC_ADDRESS all set in env.
This matches the contract that python/app_runtime/core.py already uses for
every running Truffle app — so committing this is purely additive and reveals
nothing that isn't already in the proto definitions and app_runtime package.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass


_FALLBACK_HOST = "10.22.0.1"
_FALLBACK_PORT = 80
_FALLBACK_DEVICE_NAME = "truffle-host"


@dataclass(frozen=True)
class InContainerInfo:
    """Snapshot of the in-container connection context.

    Created once per CLI invocation by `probe_in_container_device()` and
    cached. Read by the storage injection in `cli/__init__.py` and by the
    short-circuits in `cli/connect.py`.
    """

    app_id: str
    session_token: str
    grpc_address: str        # normalized "host:port"
    host: str                # "10.22.0.1"
    port: int                # 80
    device_name: str         # from System_GetID, or fallback
    serial: str              # from System_GetID, or ""
    firmware_version: str    # from System_GetInfo, or ""
    ip_address: str          # the host's LAN ip from System_GetInfo, or ""
    mac_address: str         # ""
    timezone: str            # ""
    probe_failed: bool       # True if env was set but System_GetID/Info blew up


def normalize_grpc_address(raw: str) -> str:
    """Normalize a GRPC_ADDRESS env value into a "host:port" string.

    Mirrors python/app_runtime/core.py:56-68 so the behavior matches what
    every running app already uses.
    """
    s = (raw or "").strip()
    if not s:
        return f"{_FALLBACK_HOST}:{_FALLBACK_PORT}"
    if "://" in s:
        return s
    if s.startswith("[") and "]:" in s:
        return s
    if ":" in s:
        return s
    return f"{s}:{_FALLBACK_PORT}"


def _split_host_port(normalized: str) -> tuple[str, int]:
    """Best-effort host/port split for a normalized address."""
    s = normalized
    if "://" in s:
        s = s.split("://", 1)[1]
    if s.startswith("[") and "]:" in s:
        host, _, port_s = s[1:].partition("]:")
        try:
            return host, int(port_s)
        except ValueError:
            return host, _FALLBACK_PORT
    if ":" in s:
        host, _, port_s = s.rpartition(":")
        try:
            return host, int(port_s)
        except ValueError:
            return host, _FALLBACK_PORT
    return s, _FALLBACK_PORT


def _read_env() -> tuple[str, str, str] | None:
    app_id = os.environ.get("APP_ID", "").strip()
    token = os.environ.get("APP_SESSION_TOKEN", "").strip()
    addr = os.environ.get("GRPC_ADDRESS", "").strip()
    if not (app_id and token and addr):
        return None
    return app_id, token, addr


def in_truffle_container() -> bool:
    """Cheap env-only check: are we running inside a Truffle app container?

    No RPC, no I/O. Safe to call repeatedly during CLI startup.
    """
    return _read_env() is not None


def _mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return "***"
    return f"{token[:8]}…"


_PROBE_CACHE: InContainerInfo | None = None
_PROBE_DONE: bool = False


def probe_in_container_device(*, force: bool = False) -> InContainerInfo | None:
    """Detect in-container mode and return enriched device info.

    Returns None if any of the three env vars is missing.

    If env vars are present, eagerly calls System_GetID (unauth) and
    System_GetInfo (auth, with the env session token) to populate the
    device name, serial, firmware version, ip, mac, and timezone.

    On probe failure (firmware momentarily down, envoy hiccup), falls back
    to a placeholder device name and writes a one-line warning to stderr —
    the actual command the user invoked will produce a real error if the
    firmware is genuinely unreachable, instead of failing fatally at startup.
    """
    global _PROBE_CACHE, _PROBE_DONE
    if _PROBE_DONE and not force:
        return _PROBE_CACHE
    _PROBE_DONE = True

    env = _read_env()
    if env is None:
        _PROBE_CACHE = None
        return None

    app_id, token, raw_addr = env
    grpc_address = normalize_grpc_address(raw_addr)
    host, port = _split_host_port(grpc_address)

    device_name = _FALLBACK_DEVICE_NAME
    serial = ""
    firmware_version = ""
    ip_address = ""
    mac_address = ""
    timezone = ""
    probe_failed = False

    try:
        # local imports so the env-only check stays cheap and we don't pay
        # gRPC import cost when not in a container.
        import grpc
        from google.protobuf import empty_pb2
        from truffle.os.truffleos_pb2_grpc import TruffleOSStub
        from truffle.os.system_info_pb2 import SystemGetIDRequest

        channel = grpc.insecure_channel(grpc_address)
        try:
            grpc.channel_ready_future(channel).result(timeout=5.0)
            stub = TruffleOSStub(channel)
            sid = stub.System_GetID(SystemGetIDRequest(), timeout=5.0)
            if sid.truffle_id:
                device_name = sid.truffle_id
            serial = sid.serial_number or ""
            try:
                info = stub.System_GetInfo(
                    empty_pb2.Empty(),
                    metadata=[("session", token), ("app-id", app_id)],
                    timeout=5.0,
                )
                firmware_version = (
                    info.firmware_version.version if info.HasField("firmware_version") else ""
                )
                if info.HasField("hardware_info"):
                    hw = info.hardware_info
                    ip_address = hw.ip_address or ""
                    mac_address = hw.mac_address or ""
                    timezone = hw.timezone or ""
            except Exception as exc:
                probe_failed = True
                sys.stderr.write(
                    f"warning: in-container probe got device id but System_GetInfo failed: {exc}\n"
                )
        finally:
            try:
                channel.close()
            except Exception:
                pass
    except Exception as exc:
        probe_failed = True
        sys.stderr.write(
            f"warning: in-container probe failed (env present but {grpc_address} unreachable): {exc}\n"
        )

    info_obj = InContainerInfo(
        app_id=app_id,
        session_token=token,
        grpc_address=grpc_address,
        host=host,
        port=port,
        device_name=device_name,
        serial=serial,
        firmware_version=firmware_version,
        ip_address=ip_address,
        mac_address=mac_address,
        timezone=timezone,
        probe_failed=probe_failed,
    )
    _PROBE_CACHE = info_obj
    return info_obj


def reset_probe_cache() -> None:
    """Test hook: clear the cached probe so the next call re-runs."""
    global _PROBE_CACHE, _PROBE_DONE
    _PROBE_CACHE = None
    _PROBE_DONE = False


def in_container_http_headers() -> dict[str, str]:
    """Return defensive auth headers for raw httpx calls (IF2 etc).

    Empty dict on a normal LAN dev machine — caller behaviour is unchanged.
    Inside a Truffle app container, returns the env-provided session + app-id
    so endpoints that route through the same Envoy listener still see the
    user's session, not an unauthenticated request.
    """
    info = probe_in_container_device()
    if info is None:
        return {}
    return {"session": info.session_token, "app-id": info.app_id}


def debug_summary(info: InContainerInfo) -> str:
    """One-line summary safe for debug output (token masked)."""
    return (
        f"InContainerInfo("
        f"device={info.device_name!r}, "
        f"address={info.grpc_address!r}, "
        f"app_id={info.app_id!r}, "
        f"session_token={_mask_token(info.session_token)!r}, "
        f"probe_failed={info.probe_failed}"
        f")"
    )
