from __future__ import annotations

import json
from typing import Any


SCHEMA_VERSION = "1"


def ok_payload(**fields: Any) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        **fields,
    }


def error_payload(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    next_action: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "error",
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    if next_action:
        payload["next_action"] = next_action
    payload.update({key: value for key, value in fields.items() if value is not None})
    return payload


def emit_json(payload: dict[str, Any]) -> None:
    if "schema_version" not in payload:
        payload = {"schema_version": SCHEMA_VERSION, **payload}
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def emit_error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    next_action: str | None = None,
    **fields: Any,
) -> int:
    emit_json(
        error_payload(
            code,
            message,
            retryable=retryable,
            next_action=next_action,
            **fields,
        )
    )
    return 1


def exception_details(exc: Exception, *, default_code: str) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    http_status = getattr(response, "status_code", None)
    if isinstance(http_status, int):
        if http_status == 401 or http_status == 403:
            code = "authentication_failed"
        elif http_status == 404:
            code = "service_not_found"
        elif http_status == 408:
            code = "timeout"
        elif http_status == 429:
            code = "rate_limited"
        elif http_status >= 500:
            code = "service_unavailable"
        else:
            code = default_code
        return {
            "code": code,
            "message": str(exc),
            "retryable": http_status in {408, 429} or http_status >= 500,
            "http_status": http_status,
        }
    if isinstance(exc, TimeoutError) or exc.__class__.__name__.lower().endswith("timeout"):
        return {
            "code": "timeout",
            "message": str(exc) or "Operation timed out",
            "retryable": True,
        }
    return {
        "code": default_code,
        "message": str(exc),
        "retryable": False,
    }


def truncate_text(text: str, max_bytes: int) -> tuple[str, bool, int]:
    raw = text.encode("utf-8")
    original_bytes = len(raw)
    if original_bytes <= max_bytes:
        return text, False, original_bytes
    truncated = raw[:max_bytes]
    while truncated:
        try:
            return truncated.decode("utf-8"), True, original_bytes
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return "", True, original_bytes
