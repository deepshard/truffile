from __future__ import annotations

from dataclasses import dataclass
import os

import grpc

DEFAULT_GRPC_ADDRESS = "10.22.0.1:80"
_DEFAULT_CONNECT_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class RuntimeConnectionInfo:
    app_id: str
    session_token: str
    grpc_address: str


def load_runtime_connection_info() -> RuntimeConnectionInfo:
    app_id = _required_env("APP_ID")
    session_token = _required_env("APP_SESSION_TOKEN")
    grpc_address = _normalize_grpc_address(os.getenv("GRPC_ADDRESS", DEFAULT_GRPC_ADDRESS))
    return RuntimeConnectionInfo(
        app_id=app_id,
        session_token=session_token,
        grpc_address=grpc_address,
    )


def build_auth_metadata(info: RuntimeConnectionInfo) -> list[tuple[str, str]]:
    return [("session", info.session_token), ("app-id", info.app_id)]


def init_channel(
    connection: RuntimeConnectionInfo | None = None,
    *,
    timeout_seconds: float = _DEFAULT_CONNECT_TIMEOUT_SECONDS,
) -> grpc.Channel:
    info = connection or load_runtime_connection_info()
    channel = grpc.insecure_channel(info.grpc_address)
    grpc.channel_ready_future(channel).result(timeout=timeout_seconds)
    return channel


def close_channel(channel: grpc.Channel) -> None:
    channel.close()


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value == "":
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _normalize_grpc_address(address: str) -> str:
    raw = address.strip()
    if raw == "":
        return DEFAULT_GRPC_ADDRESS
    # Keep URI forms unchanged.
    if "://" in raw:
        return raw
    # Preserve bracketed IPv6 form if port already present.
    if raw.startswith("[") and "]:" in raw:
        return raw
    if ":" in raw:
        return raw
    return f"{raw}:80"
