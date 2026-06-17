#!/usr/bin/env python3
"""Foreground MCP proxy and harness-friendly app object for Viator."""

from __future__ import annotations

import argparse
import atexit
import json
import logging
import os
import sys
import time
from typing import Any

from truffile.app_runtime.errors import AppAuthError, AppRuntimeFailure, ErrorReporter
from truffile.app_runtime.jsonrpc import parse_jsonrpc_payload as _parse_jsonrpc_payload
from truffile.app_runtime.remote_mcp import (
    RemoteMcpClient,
    RemoteMcpProxyServer,
    RemoteMcpTool,
    RemoteMcpToolOverride,
    one_shot_payload_is_complete as _one_shot_payload_is_complete,
    read_upstream_response as _read_upstream_response,
    wrap_tool_result,
)

from config import MCP_HOST, MCP_PORT, VIATOR_MCP_BASE, build_default_headers
from tools import TOOLS_BY_NAME


LOGGER = logging.getLogger("viator.foreground")
LOGGER.setLevel(logging.INFO)

_EXPECTED_TOOLS = {"get_experience_details", "search_experiences"}
_LOCAL_SEARCH_ARGS = {"include_images", "include_raw"}
_LOCAL_DETAIL_ARGS = {"include_images", "include_raw", "include_details", "include_reviews", "max_chars", "review_limit"}
_RATE_LIMIT_ATTEMPTS = 3
_DEFAULT_RATE_LIMIT_RETRY_DELAY_SECONDS = 1.0
_MAX_RATE_LIMIT_RETRY_DELAY_SECONDS = 5.0
_SEARCH_EXPERIENCES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "searchTerm": {
            "type": "string",
            "description": "Destination plus interests, for example 'Paris food tour' or 'accessible New York museum tour'.",
        },
        "startDate": {"type": "string", "description": "Start date in YYYY-MM-DD format."},
        "endDate": {"type": "string", "description": "End date in YYYY-MM-DD format."},
        "limit": {"type": "integer", "description": "Maximum results to return.", "minimum": 1, "maximum": 50},
        "currency": {"type": "string", "description": "ISO 4217 currency code such as USD, EUR, or GBP."},
        "locale": {"type": "string", "description": "Locale tag such as en-US, fr-FR, or es-ES."},
        "sessionId": {"type": "string", "description": "Caller-provided stable session ID."},
        "include_images": {
            "type": "boolean",
            "description": "Include one image URL per experience. Defaults to false for compact results.",
            "default": False,
        },
        "include_raw": {
            "type": "boolean",
            "description": "Include the raw Viator MCP result for debugging. Defaults to false.",
            "default": False,
        },
    },
    "required": ["startDate", "endDate", "sessionId"],
    "additionalProperties": False,
}
_GET_EXPERIENCE_DETAILS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "code": {"type": "string", "description": "Viator product/experience code returned by search_experiences."},
        "currency": {"type": "string", "description": "Optional ISO 4217 currency code such as USD, EUR, or GBP."},
        "locale": {"type": "string", "description": "Locale tag such as en-US, fr-FR, or es-ES."},
        "sessionId": {"type": "string", "description": "Caller-provided stable session ID."},
        "max_chars": {
            "type": "integer",
            "description": "Maximum description characters to return. Defaults to 500; maximum is 4000.",
            "minimum": 0,
            "maximum": 4000,
            "default": 500,
        },
        "include_details": {
            "type": "boolean",
            "description": "Include extra planning fields such as meeting point, inclusions, accessibility, and cancellation terms when available.",
            "default": False,
        },
        "include_reviews": {
            "type": "boolean",
            "description": "Include bounded review snippets when Viator returns reviews. Defaults to false.",
            "default": False,
        },
        "review_limit": {
            "type": "integer",
            "description": "Maximum reviews to return when include_reviews is true. Defaults to 3; maximum is 10.",
            "minimum": 1,
            "maximum": 10,
            "default": 3,
        },
        "include_images": {
            "type": "boolean",
            "description": "Include the experience image URL. Defaults to false for compact results.",
            "default": False,
        },
        "include_raw": {
            "type": "boolean",
            "description": "Include the raw Viator MCP result for debugging. Defaults to false.",
            "default": False,
        },
    },
    "required": ["code", "sessionId"],
    "additionalProperties": False,
}
_TOOL_OVERRIDES = [
    RemoteMcpToolOverride(
        remote_name="search_experiences",
        description=TOOLS_BY_NAME["search_experiences"].description,
        input_schema=_SEARCH_EXPERIENCES_SCHEMA,
        annotations=dict(TOOLS_BY_NAME["search_experiences"].annotations),
    ),
    RemoteMcpToolOverride(
        remote_name="get_experience_details",
        description=TOOLS_BY_NAME["get_experience_details"].description,
        input_schema=_GET_EXPERIENCE_DETAILS_SCHEMA,
        annotations=dict(TOOLS_BY_NAME["get_experience_details"].annotations),
    ),
]


def _eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _is_present(value: Any) -> bool:
    return value not in (None, "", [], {})


def _walk_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(_walk_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk_values(child))
    return values


def _first_value(data: Any, keys: set[str]) -> Any:
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = key.lower().replace("_", "").replace("-", "")
            if normalized in keys and value not in (None, "", [], {}):
                return value
        for value in data.values():
            found = _first_value(value, keys)
            if found not in (None, "", [], {}):
                return found
    elif isinstance(data, list):
        for item in data:
            found = _first_value(item, keys)
            if found not in (None, "", [], {}):
                return found
    return None


def _compact_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if _is_present(value)}


def _bool_arg(arguments: dict[str, Any], key: str, *, default: bool = False) -> bool:
    value = arguments.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _int_arg(arguments: dict[str, Any], key: str, *, default: int, minimum: int, maximum: int) -> int:
    value = arguments.get(key, default)
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
        return int(parsed) if parsed.is_integer() else parsed
    return None


def _rounded_rating(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return round(float(number), 1)


def _string(value: Any) -> str | None:
    if value in (None, "", [], {}):
        return None
    text = str(value).strip()
    return text or None


def _structured_payload(wrapped: dict[str, Any]) -> dict[str, Any]:
    provider_result = wrapped.get("provider_result")
    if isinstance(provider_result, dict) and isinstance(provider_result.get("structuredContent"), dict):
        return provider_result["structuredContent"]
    text = wrapped.get("text")
    if isinstance(text, str) and text.strip().startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return wrapped


def _trim_text(value: Any, max_chars: int) -> tuple[str | None, bool]:
    text = _string(value)
    if text is None:
        return None, False
    if max_chars <= 0:
        return None, True
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip(), True


def _normalize_duration(duration: Any) -> dict[str, Any]:
    if not isinstance(duration, dict):
        return {}
    fixed = _number(duration.get("fixedDurationInMinutes"))
    if fixed is not None:
        return {"duration_minutes": fixed}
    start = _number(duration.get("variableDurationFromMinutes"))
    end = _number(duration.get("variableDurationToMinutes"))
    if start is not None or end is not None:
        return {"duration_minutes_range": _compact_dict({"from": start, "to": end})}
    return {}


def _normalize_experience_summary(item: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    key_attributes = item.get("keyAttributes") if isinstance(item.get("keyAttributes"), dict) else {}
    price_amount = _number(item.get("fromPrice") or item.get("price") or item.get("amount"))
    currency = _string(item.get("currency") or item.get("currencyCode") or arguments.get("currency"))
    summary = _compact_dict(
        {
            "code": _string(item.get("code") or item.get("productCode") or item.get("product_code")),
            "title": _string(item.get("title")),
            "price_from": _compact_dict({"amount": price_amount, "currency": currency}) if price_amount is not None else None,
            "rating": _rounded_rating(item.get("rating")),
            "review_count": _number(item.get("reviewCount") or item.get("review_count")),
            "category": _string(key_attributes.get("mainCategory") or item.get("category")),
            "free_cancellation": item.get("freeCancellation") if isinstance(item.get("freeCancellation"), bool) else None,
            "product_url": _string(item.get("clickOffToLander") or item.get("clickOffToPDP") or item.get("productUrl") or item.get("url")),
        }
    )
    summary.update(_normalize_duration(item.get("duration")))
    if _bool_arg(arguments, "include_images"):
        image_url = _string(item.get("thumbnail") or item.get("imageUrl") or item.get("image_url"))
        if image_url:
            summary["image_url"] = image_url
    return summary


def _planning_details(data: Any) -> dict[str, Any]:
    search_space = _walk_values(data)
    return _compact_dict(
        {
            "meeting_point": _first_value(search_space, {"meetingpoint", "meetinglocation", "departurepoint"}),
            "start_times": _first_value(search_space, {"starttimes", "starttime", "departuretimes", "times"}),
            "inclusions": _first_value(search_space, {"inclusions", "included", "whatsincluded"}),
            "exclusions": _first_value(search_space, {"exclusions", "excluded", "whatsnotincluded"}),
            "cancellation_terms": _first_value(search_space, {"cancellationpolicy", "cancellationterms", "cancellation"}),
            "accessibility": _first_value(search_space, {"accessibility", "accessibilitynotes", "accessible"}),
            "group_size": _first_value(search_space, {"groupsize", "maxgroupsize", "maximumgroupsize"}),
            "age_limits": _first_value(search_space, {"agelimits", "minimumage", "minage", "agerange"}),
            "languages": _first_value(search_space, {"languages", "guidelanguages", "language"}),
        }
    )


def _normalize_review(item: Any, max_chars: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    text, truncated = _trim_text(
        item.get("text") or item.get("reviewText") or item.get("comment") or item.get("description"),
        max_chars,
    )
    return _compact_dict(
        {
            "rating": _rounded_rating(item.get("rating")),
            "title": _string(item.get("title")),
            "text": text,
            "text_truncated": truncated if text or truncated else None,
            "traveler": _string(item.get("travelerName") or item.get("userName") or item.get("author")),
        }
    )


def _normalize_reviews(data: Any, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    reviews = _first_value(data, {"reviews", "customerreviews", "review"})
    if isinstance(reviews, dict):
        candidate = reviews.get("items") or reviews.get("reviews") or reviews.get("data")
        reviews = candidate if isinstance(candidate, list) else [reviews]
    if not isinstance(reviews, list):
        return []
    limit = _int_arg(arguments, "review_limit", default=3, minimum=1, maximum=10)
    normalized = [_normalize_review(item, 500) for item in reviews[:limit]]
    return [item for item in normalized if item]


def _compact_error(tool_name: str, wrapped: dict[str, Any]) -> dict[str, Any]:
    return _compact_dict(
        {
            "status": wrapped.get("status") or "error",
            "tool": tool_name,
            "message": _string(wrapped.get("message") or wrapped.get("text")),
        }
    )


def _compact_search_result(wrapped: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    if wrapped.get("status") != "success":
        return _compact_error("search_experiences", wrapped)
    structured = _structured_payload(wrapped)
    experiences = structured.get("experiences") if isinstance(structured.get("experiences"), list) else wrapped.get("experiences")
    if not isinstance(experiences, list):
        experiences = []
    normalized = [item for item in (_normalize_experience_summary(item, arguments) for item in experiences) if item]
    out = _compact_dict(
        {
            "status": "success",
            "tool": "search_experiences",
            "sessionId": _string(structured.get("sessionId") or wrapped.get("sessionId")),
            "count": len(normalized),
            "experiences": normalized,
        }
    )
    if _bool_arg(arguments, "include_raw"):
        out["provider_result"] = wrapped.get("provider_result")
    return out


def _compact_details_result(wrapped: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    if wrapped.get("status") != "success":
        return _compact_error("get_experience_details", wrapped)
    structured = _structured_payload(wrapped)
    details = structured.get("experienceDetails") or structured.get("experience") or wrapped.get("experienceDetails")
    if not isinstance(details, dict):
        details = {}
    max_chars = _int_arg(arguments, "max_chars", default=500, minimum=0, maximum=4000)
    description, description_truncated = _trim_text(details.get("description"), max_chars)
    experience = _compact_dict(
        {
            "code": _string(details.get("code") or details.get("productCode") or arguments.get("code")),
            "title": _string(details.get("title")),
            "description": description,
            "description_truncated": description_truncated if description or description_truncated else None,
            "rating": _rounded_rating(details.get("rating")),
            "review_count": _number(details.get("reviewCount") or details.get("review_count")),
            "free_cancellation": details.get("freeCancellation") if isinstance(details.get("freeCancellation"), bool) else None,
            "product_url": _string(details.get("clickOffToPDP") or details.get("clickOffToLander") or details.get("productUrl") or details.get("url")),
            "currency": _string(details.get("currency") or details.get("currencyCode") or arguments.get("currency")),
        }
    )
    if _bool_arg(arguments, "include_images"):
        image_url = _string(details.get("thumbnail") or details.get("imageUrl") or details.get("image_url"))
        if image_url:
            experience["image_url"] = image_url
    if _bool_arg(arguments, "include_details"):
        planning_details = _planning_details(details)
        if planning_details:
            experience["details"] = planning_details
    if _bool_arg(arguments, "include_reviews"):
        reviews = _normalize_reviews(details, arguments)
        if reviews:
            experience["reviews"] = reviews
    out = _compact_dict(
        {
            "status": "success",
            "tool": "get_experience_details",
            "sessionId": _string(structured.get("sessionId") or wrapped.get("sessionId")),
            "experience": experience,
        }
    )
    if _bool_arg(arguments, "include_raw"):
        out["provider_result"] = wrapped.get("provider_result")
    return out


def _compact_viator_result(tool_name: str, wrapped: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "search_experiences":
        return _compact_search_result(wrapped, arguments)
    if tool_name == "get_experience_details":
        return _compact_details_result(wrapped, arguments)
    return wrapped


def _remote_arguments(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    local_args = _LOCAL_SEARCH_ARGS if tool_name == "search_experiences" else _LOCAL_DETAIL_ARGS
    return {key: value for key, value in dict(arguments or {}).items() if key not in local_args}


def _retry_delay_seconds(headers: dict[str, str]) -> float:
    retry_after = ""
    for key, value in headers.items():
        if key.lower() == "retry-after":
            retry_after = str(value).strip()
            break
    if retry_after:
        try:
            return min(_MAX_RATE_LIMIT_RETRY_DELAY_SECONDS, max(0.0, float(retry_after)))
        except ValueError:
            return _DEFAULT_RATE_LIMIT_RETRY_DELAY_SECONDS
    try:
        configured = float(os.getenv("VIATOR_RATE_LIMIT_RETRY_DELAY_SECONDS", str(_DEFAULT_RATE_LIMIT_RETRY_DELAY_SECONDS)))
    except ValueError:
        configured = _DEFAULT_RATE_LIMIT_RETRY_DELAY_SECONDS
    return min(_MAX_RATE_LIMIT_RETRY_DELAY_SECONDS, max(0.0, configured))


def _parsed_error_message(parsed: dict[str, Any] | None) -> str:
    if not isinstance(parsed, dict) or "error" not in parsed:
        return ""
    error = parsed["error"]
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(error)


def _is_rate_limited(status: int, parsed: dict[str, Any] | None, raw: str) -> bool:
    if status == 429:
        return True
    message = f"{_parsed_error_message(parsed)} {raw[:300]}".lower()
    return "rate limit" in message or "rate-limit" in message or "too many requests" in message


def _rate_limited_result(tool_name: str, attempts: int, retry_after_seconds: float) -> dict[str, Any]:
    return {
        "status": "rate_limited",
        "tool": tool_name,
        "message": f"Viator rate limit reached after {attempts} attempts.",
        "retry_after_seconds": int(retry_after_seconds) if retry_after_seconds.is_integer() else retry_after_seconds,
        "attempts": attempts,
    }


def _wrap_stub_result(name: str, arguments: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return _compact_viator_result(name, wrap_tool_result(name, _remote_arguments(name, arguments), result), arguments)


class ViatorRemoteMcpClient(RemoteMcpClient):
    def __init__(
        self,
        *,
        remote_url: str,
        default_headers: dict[str, str] | None = None,
        post_jsonrpc: Any = None,
    ) -> None:
        headers = dict(default_headers or {})

        def adapter(remote_url: str, payload: dict[str, Any]) -> tuple[int, dict[str, str], dict[str, Any] | None, str]:
            return post_jsonrpc(
                remote_url,
                payload,
                default_headers=headers,
                session_id=self._session_id,
                timeout=30,
            )

        super().__init__(
            remote_url=remote_url,
            default_headers=headers,
            tool_overrides=_TOOL_OVERRIDES,
            app_name="Viator",
            protocol_version="2025-06-18",
            post_jsonrpc=adapter if post_jsonrpc is not None else None,
        )

    def verify(self) -> tuple[bool, str]:
        try:
            tools = self.list_tools()
        except AppAuthError:
            return False, "Viator verification failed: client IP is not whitelisted"
        except AppRuntimeFailure as exc:
            return False, f"Viator verification failed: {exc}"
        except Exception as exc:
            return False, f"Viator verification failed: {exc}"

        tool_names = sorted(tool.public_name for tool in tools)
        missing = sorted(_EXPECTED_TOOLS - set(tool_names))
        if missing:
            return False, f"Viator verification failed: missing tools={','.join(missing)}"
        return True, f"Viator MCP verified. tools={','.join(tool_names)}"

    def _ensure_initialized(self) -> None:
        try:
            super()._ensure_initialized()
        except AppAuthError as exc:
            if "initialize unauthorized" in str(exc):
                raise AppAuthError("Viator initialize forbidden; client IP is not whitelisted") from exc
            raise

    def list_tools(self) -> list[RemoteMcpTool]:
        try:
            return super().list_tools()
        except AppAuthError as exc:
            if "tools/list unauthorized" in str(exc):
                raise AppAuthError("Viator tools/list forbidden; client IP is not whitelisted") from exc
            raise

    def _call_tool_with_retry(self, public_name: str, remote_name: str, arguments: dict[str, Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": remote_name, "arguments": dict(arguments or {})},
        }
        retry_after_seconds = _DEFAULT_RATE_LIMIT_RETRY_DELAY_SECONDS
        for attempt in range(1, _RATE_LIMIT_ATTEMPTS + 1):
            status, headers, parsed, raw = self.send_jsonrpc(payload)
            if status in {401, 403} and self._refresh_auth():
                self._ensure_initialized()
                status, headers, parsed, raw = self.send_jsonrpc(payload)
            if _is_rate_limited(status, parsed, raw):
                retry_after_seconds = _retry_delay_seconds(headers)
                if attempt < _RATE_LIMIT_ATTEMPTS:
                    time.sleep(retry_after_seconds)
                    continue
                return _rate_limited_result(public_name, attempt, retry_after_seconds)
            if status in {401, 403}:
                raise AppAuthError(f"Viator tool '{public_name}' forbidden; client IP is not whitelisted")
            if status >= 400:
                raise AppRuntimeFailure(f"Viator tool '{public_name}' failed with HTTP {status}: {raw[:300]}")
            if parsed and parsed.get("error"):
                message_text = _parsed_error_message(parsed)
                if "unauthorized" in message_text.lower() and self._refresh_auth():
                    self._ensure_initialized()
                    status, headers, parsed, raw = self.send_jsonrpc(payload)
                    if _is_rate_limited(status, parsed, raw):
                        retry_after_seconds = _retry_delay_seconds(headers)
                        if attempt < _RATE_LIMIT_ATTEMPTS:
                            time.sleep(retry_after_seconds)
                            continue
                        return _rate_limited_result(public_name, attempt, retry_after_seconds)
                    if status < 400 and parsed and not parsed.get("error"):
                        return parsed.get("result")
                if "unauthorized" in message_text.lower():
                    raise AppAuthError(f"Viator tool '{public_name}' forbidden; client IP is not whitelisted")
                raise AppRuntimeFailure(f"Viator tool '{public_name}' returned error: {message_text}")
            if not parsed or "result" not in parsed:
                raise AppRuntimeFailure(f"Viator tool '{public_name}' returned no result")
            return parsed["result"]
        return _rate_limited_result(public_name, _RATE_LIMIT_ATTEMPTS, retry_after_seconds)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._ensure_initialized()
        if not self._tool_name_map:
            self.list_tools()
        remote_name = self._tool_name_map.get(name, name)
        local_arguments = dict(arguments or {})
        remote_arguments = _remote_arguments(name, local_arguments)
        result = self._call_tool_with_retry(name, remote_name, remote_arguments)
        if isinstance(result, dict) and result.get("status") == "rate_limited":
            return result
        wrapped = wrap_tool_result(name, remote_arguments, result)
        return _compact_viator_result(name, wrapped, local_arguments)


class _StubViatorRemoteMcpClient:
    def verify(self) -> tuple[bool, str]:
        return True, "Viator MCP verified. tools=get_experience_details,search_experiences"

    def list_tools(self) -> list[RemoteMcpTool]:
        return [
            RemoteMcpTool(
                remote_name="search_experiences",
                public_name="search_experiences",
                description=_TOOL_OVERRIDES[0].description or "Search Viator experiences.",
                input_schema=_SEARCH_EXPERIENCES_SCHEMA,
                annotations={"readOnlyHint": True, "destructiveHint": False},
            ),
            RemoteMcpTool(
                remote_name="get_experience_details",
                public_name="get_experience_details",
                description=_TOOL_OVERRIDES[1].description or "Get Viator experience details.",
                input_schema=_GET_EXPERIENCE_DETAILS_SCHEMA,
                annotations={"readOnlyHint": True, "destructiveHint": False},
            ),
        ]

    def tool_to_mcp_dict(self, tool: RemoteMcpTool) -> dict[str, Any]:
        return RemoteMcpClient.tool_to_mcp_dict(tool)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return _wrap_stub_result(
            name,
            arguments,
            {
                "content": [{"type": "text", "text": f"stub:{name}"}],
                "structuredContent": {"name": name, "arguments": _remote_arguments(name, arguments)},
                "isError": False,
            },
        )

    def send_jsonrpc(self, payload: dict[str, Any]) -> tuple[int, dict[str, str], dict[str, Any] | None, str]:
        method = str(payload.get("method", "") or "")
        if method == "initialize":
            return 200, {}, {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"protocolVersion": "2025-06-18"}}, "{}"
        if method == "tools/list":
            return (
                200,
                {},
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {"tools": [self.tool_to_mcp_dict(tool) for tool in self.list_tools()]},
                },
                "{}",
            )
        if method == "tools/call":
            params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
            return (
                200,
                {},
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": self.call_tool(str(params.get("name", "") or ""), params.get("arguments") or {}),
                },
                "{}",
            )
        return 200, {}, {"jsonrpc": "2.0", "id": payload.get("id"), "result": {}}, "{}"

    def close(self) -> None:
        return None


class ViatorForegroundApp:
    def __init__(self, client: Any | None = None) -> None:
        self.name = "viator"
        self.logger = LOGGER
        self._error_reporter = ErrorReporter(logger=self.logger, app_name=self.name)
        self._client = client

    def build_client(self) -> ViatorRemoteMcpClient:
        if os.getenv("APP_STORE_USE_TEST_STUBS") == "1":
            return _StubViatorRemoteMcpClient()  # type: ignore[return-value]
        return ViatorRemoteMcpClient(
            remote_url=VIATOR_MCP_BASE,
            default_headers=build_default_headers(),
        )

    def get_client(self) -> Any:
        if self._client is None:
            self._client = self.build_client()
        return self._client

    def set_client(self, client: Any) -> None:
        self.reset_for_test()
        self._client = client

    def reset_for_test(self) -> None:
        if self._client is not None:
            close = getattr(self._client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    self.logger.exception("Failed closing Viator MCP client")
        self._client = None

    def logger_names(self) -> list[str]:
        return [self.logger.name]

    def list_tools(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        client = self.get_client()
        for tool in client.list_tools():
            if isinstance(tool, RemoteMcpTool):
                out.append(client.tool_to_mcp_dict(tool))
            elif isinstance(tool, dict):
                out.append(tool)
        return out

    def list_prompts(self) -> list[dict[str, str]]:
        return []

    async def invoke_tool(self, name: str, **arguments: Any) -> Any:
        try:
            return self.get_client().call_tool(name, arguments)
        except Exception as exc:
            await self._error_reporter.report_foreground_exception(exc, tool_name=name)
            raise

    def verify(self) -> tuple[bool, str]:
        client = self.build_client()
        try:
            return client.verify()
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def run(self) -> None:
        client = self.build_client()
        LOGGER.info(
            "Starting Viator MCP proxy on %s:%d -> %s",
            MCP_HOST,
            MCP_PORT,
            client.remote_url,
        )
        try:
            RemoteMcpProxyServer(client=client, host=MCP_HOST, port=MCP_PORT).serve_forever()
        except KeyboardInterrupt:
            LOGGER.info("Viator MCP proxy stopped")


app = ViatorForegroundApp()
ViatorMCPProxyHandler = RemoteMcpProxyServer._make_handler()


def verify() -> int:
    try:
        ok, message = app.verify()
    except Exception as exc:
        _eprint(f"Viator verification failed: {exc}")
        return 1
    if ok:
        print(message, flush=True)
        return 0
    _eprint(message)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Viator MCP proxy")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify Viator MCP by calling initialize + tools/list.",
    )
    args = parser.parse_args()
    if args.verify:
        return verify()
    app.run()
    return 0


def set_client(client: Any) -> None:
    app.set_client(client)


def reset_for_test() -> None:
    app.reset_for_test()


atexit.register(reset_for_test)


if __name__ == "__main__":
    raise SystemExit(main())
