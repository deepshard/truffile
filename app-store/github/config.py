from __future__ import annotations

import os

TOKEN_EXPORT_TOOL_NAME = "truffle_get_github_access_token_for_local_handoff"

MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))

GITHUB_MCP_BASE = os.getenv("GITHUB_MCP_BASE", "https://api.githubcopilot.com/mcp/").strip()
GITHUB_MCP_TOOLSETS = os.getenv("GITHUB_MCP_TOOLSETS", "all").strip()
GITHUB_MCP_TOOLS = os.getenv("GITHUB_MCP_TOOLS", "").strip()
GITHUB_MCP_EXCLUDE_TOOLS = os.getenv("GITHUB_MCP_EXCLUDE_TOOLS", "").strip()
GITHUB_MCP_READONLY = os.getenv("GITHUB_MCP_READONLY", "").strip()
GITHUB_MCP_LOCKDOWN = os.getenv("GITHUB_MCP_LOCKDOWN", "").strip()
GITHUB_MCP_INSIDERS = os.getenv("GITHUB_MCP_INSIDERS", "").strip()

GITHUB_API_BASE = os.getenv("GITHUB_API_BASE", "https://api.github.com").rstrip("/")
MAX_ITEMS_PER_QUERY = max(1, int(os.getenv("GITHUB_BG_MAX_ITEMS", "8")))
MAX_ORGS_TO_SCAN = max(0, int(os.getenv("GITHUB_BG_MAX_ORGS", "25")))
AUTH_FAILURE_REPORT_THRESHOLD = max(1, int(os.getenv("GITHUB_BG_AUTH_FAILURE_THRESHOLD", "3")))


def load_access_token() -> str:
    from auth import GitHubAuth

    return GitHubAuth().load_access_token()


def build_default_headers(token: str) -> dict[str, str]:
    headers: dict[str, str] = {
        "Authorization": f"Bearer {token}",
    }
    if GITHUB_MCP_TOOLSETS:
        headers["X-MCP-Toolsets"] = GITHUB_MCP_TOOLSETS
    if GITHUB_MCP_TOOLS:
        headers["X-MCP-Tools"] = GITHUB_MCP_TOOLS
    if GITHUB_MCP_EXCLUDE_TOOLS:
        headers["X-MCP-Exclude-Tools"] = GITHUB_MCP_EXCLUDE_TOOLS
    if GITHUB_MCP_READONLY:
        headers["X-MCP-Readonly"] = GITHUB_MCP_READONLY
    if GITHUB_MCP_LOCKDOWN:
        headers["X-MCP-Lockdown"] = GITHUB_MCP_LOCKDOWN
    if GITHUB_MCP_INSIDERS:
        headers["X-MCP-Insiders"] = GITHUB_MCP_INSIDERS
    return headers


def mask_token(raw: str) -> str:
    if len(raw) <= 10:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"
