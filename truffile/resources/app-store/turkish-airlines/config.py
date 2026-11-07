from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_TOKEN_FILE = Path("/root/.turkish-airlines-oauth/tokens.json")
DEFAULT_DATA_DIR = Path(os.getenv("TURKISH_AIRLINES_DATA_DIR", "/root/.turkish-airlines-oauth")).expanduser()

MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
TURKISH_AIRLINES_MCP_BASE = os.getenv("TURKISH_AIRLINES_MCP_BASE", "https://mcp.turkishtechlab.com/mcp").strip()
TURKISH_AIRLINES_AUTH_TOKEN_ENDPOINT = os.getenv("TURKISH_AIRLINES_AUTH_TOKEN_ENDPOINT", "https://mcp.turkishtechlab.com/token").strip()
TURKISH_AIRLINES_OAUTH_RESOURCE = os.getenv("TURKISH_AIRLINES_OAUTH_RESOURCE", "https://mcp.turkishtechlab.com").strip()
TURKISH_AIRLINES_USER_AGENT = os.getenv("TURKISH_AIRLINES_USER_AGENT", "Truffle/1.0").strip()
TURKISH_AIRLINES_API_BASE = os.getenv("TURKISH_AIRLINES_API_BASE", "https://api.turkishairlines.com").strip().rstrip("/")
TURKISH_AIRLINES_OAUTH_APP_VAR_KEY = "turkish_airlines_oauth_state"


def resolve_token_file() -> Path:
    token_file_raw = str(os.getenv("TURKISH_AIRLINES_OAUTH_TOKEN_FILE", "")).strip()
    return Path(token_file_raw) if token_file_raw else DEFAULT_TOKEN_FILE


def load_oauth_token_payload() -> dict[str, Any]:
    token_path = resolve_token_file()
    if not token_path.exists():
        raise RuntimeError(f"Turkish Airlines OAuth token file not found: {token_path}")
    try:
        payload = json.loads(token_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"failed to read Turkish Airlines OAuth token file: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Turkish Airlines OAuth token payload must be a JSON object")
    return payload


def load_access_token() -> str:
    payload = load_oauth_token_payload()
    token = str(payload.get("access_token", "") or "").strip()
    if not token:
        raise RuntimeError("Turkish Airlines OAuth token payload missing access_token")
    return token


def build_default_headers() -> dict[str, str]:
    return {"User-Agent": TURKISH_AIRLINES_USER_AGENT} if TURKISH_AIRLINES_USER_AGENT else {}


def mask_token(raw: str) -> str:
    if len(raw) <= 10:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"