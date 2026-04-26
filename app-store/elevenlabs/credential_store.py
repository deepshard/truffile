from __future__ import annotations

import json
import os
from pathlib import Path

import grpc

from config import ELEVENLABS_API_KEY, ELEVENLABS_API_KEY_APP_VAR, ELEVENLABS_CREDENTIAL_FILE


def runtime_app_vars_enabled() -> bool:
    return bool(
        str(os.getenv("APP_ID", "")).strip()
        and str(os.getenv("APP_SESSION_TOKEN", "")).strip()
        and str(os.getenv("GRPC_ADDRESS", "")).strip()
    )


def load_api_key() -> str:
    from_app_var = _load_from_app_var()
    if from_app_var:
        _save_to_file(from_app_var)
        return from_app_var

    from_file = _load_from_file()
    if from_file:
        _save_to_app_var(from_file)
        return from_file

    return ELEVENLABS_API_KEY


def save_api_key(api_key: str) -> None:
    cleaned = api_key.strip()
    if not cleaned:
        raise ValueError("API key is required")
    _save_to_file(cleaned)
    _save_to_app_var(cleaned)


def api_key_source() -> str:
    if _load_from_app_var():
        return "app_var"
    if _load_from_file():
        return "file"
    if ELEVENLABS_API_KEY:
        return "environment"
    return "missing"


def _load_from_file() -> str:
    try:
        payload = json.loads(ELEVENLABS_CREDENTIAL_FILE.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("api_key", "") or "").strip()


def _save_to_file(api_key: str) -> None:
    ELEVENLABS_CREDENTIAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    ELEVENLABS_CREDENTIAL_FILE.write_text(
        json.dumps({"api_key": api_key}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_from_app_var() -> str:
    if not runtime_app_vars_enabled():
        return ""
    try:
        from app_runtime.core import build_auth_metadata, init_channel, load_runtime_connection_info
        from truffle.app import app_runtime_pb2, app_runtime_pb2_grpc

        connection = load_runtime_connection_info()
        with init_channel() as channel:
            stub = app_runtime_pb2_grpc.AppRuntimeServiceStub(channel)
            response = stub.GetAppVar(
                app_runtime_pb2.AppRuntimeGetAppVarRequest(key=ELEVENLABS_API_KEY_APP_VAR),
                metadata=build_auth_metadata(connection),
            )
            return str(response.value or "").strip()
    except grpc.RpcError as exc:
        if exc.code() == grpc.StatusCode.NOT_FOUND:
            return ""
        return ""
    except Exception:
        return ""


def _save_to_app_var(api_key: str) -> None:
    if not runtime_app_vars_enabled():
        return
    try:
        from app_runtime.core import build_auth_metadata, init_channel, load_runtime_connection_info
        from truffle.app import app_runtime_pb2, app_runtime_pb2_grpc

        connection = load_runtime_connection_info()
        with init_channel() as channel:
            stub = app_runtime_pb2_grpc.AppRuntimeServiceStub(channel)
            stub.SetAppVar(
                app_runtime_pb2.AppRuntimeSetAppVarRequest(
                    key=ELEVENLABS_API_KEY_APP_VAR,
                    value=api_key,
                ),
                metadata=build_auth_metadata(connection),
            )
    except Exception:
        return
