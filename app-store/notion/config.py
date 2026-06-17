from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_TOKEN_FILE = Path("/root/.notion-oauth/tokens.json")
DEFAULT_DATA_DIR = Path(os.getenv("NOTION_DATA_DIR", "/root/.notion-oauth")).expanduser()

MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
NOTION_MCP_BASE = os.getenv("NOTION_MCP_BASE", "https://mcp.notion.com/mcp").strip()
NOTION_AUTH_TOKEN_ENDPOINT = os.getenv("NOTION_AUTH_TOKEN_ENDPOINT", "https://mcp.notion.com/token").strip()
NOTION_OAUTH_RESOURCE = os.getenv("NOTION_OAUTH_RESOURCE", "https://mcp.notion.com").strip()
NOTION_USER_AGENT = os.getenv("NOTION_USER_AGENT", "Truffle/1.0").strip()
NOTION_API_BASE = os.getenv("NOTION_API_BASE", "https://api.notion.com/v1").strip().rstrip("/")
NOTION_API_VERSION = os.getenv("NOTION_API_VERSION", "2025-09-03").strip() or "2025-09-03"
NOTION_BACKGROUND_SOURCE = os.getenv("NOTION_BACKGROUND_SOURCE", "mcp").strip().lower() or "mcp"
NOTION_BACKGROUND_MAX_ITEMS = max(1, int(os.getenv("NOTION_BACKGROUND_MAX_ITEMS", "20")))
NOTION_OAUTH_APP_VAR_KEY = "notion_oauth_state"
TOKEN_EXPORT_TOOL_NAME = "notion_export_installed_token"


def resolve_token_file() -> Path:
    token_file_raw = str(os.getenv("NOTION_OAUTH_TOKEN_FILE", "")).strip()
    return Path(token_file_raw) if token_file_raw else DEFAULT_TOKEN_FILE


def load_oauth_token_payload() -> dict[str, Any]:
    token_path = resolve_token_file()
    if not token_path.exists():
        raise RuntimeError(f"Notion OAuth token file not found: {token_path}")
    try:
        payload = json.loads(token_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"failed to read Notion OAuth token file: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Notion OAuth token payload must be a JSON object")
    return payload


def load_access_token() -> str:
    payload = load_oauth_token_payload()
    token = str(payload.get("access_token", "") or "").strip()
    if not token:
        raise RuntimeError("Notion OAuth token payload missing access_token")
    return token


def build_default_headers() -> dict[str, str]:
    return {"User-Agent": NOTION_USER_AGENT} if NOTION_USER_AGENT else {}


def mask_token(raw: str) -> str:
    if len(raw) <= 10:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"
