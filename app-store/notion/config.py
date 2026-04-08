from __future__ import annotations

import os
import shutil

DEFAULT_NOTION_VERSION = os.getenv("NOTION_VERSION", "2025-09-03").strip() or "2025-09-03"

MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
LOCAL_MCP_HOST = os.getenv("NOTION_MCP_LOCAL_HOST", "127.0.0.1")
LOCAL_MCP_PATH = os.getenv("NOTION_MCP_PATH", "/mcp").strip() or "/mcp"
LOCAL_STARTUP_TIMEOUT_SECONDS = max(1.0, float(os.getenv("NOTION_MCP_STARTUP_TIMEOUT_SECONDS", "15")))
TOKEN_EXPORT_TOOL_NAME = "notion_export_installed_token"


def load_access_token() -> str:
    from auth import NotionAuth

    return NotionAuth().get_access_token()


def resolve_binary() -> str:
    for candidate in ("notion-mcp-server", "/usr/local/bin/notion-mcp-server", "/usr/bin/notion-mcp-server"):
        path = shutil.which(candidate) if "/" not in candidate else candidate
        if path and os.path.exists(path):
            return path
    raise RuntimeError("notion-mcp-server binary not found; install @notionhq/notion-mcp-server first")


def mask_token(raw: str) -> str:
    if len(raw) <= 10:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"
