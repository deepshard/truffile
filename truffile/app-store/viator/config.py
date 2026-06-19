from __future__ import annotations

import os


MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
VIATOR_MCP_BASE = os.getenv("VIATOR_MCP_BASE", "https://exp-app-mcp.prod.ep.viator.com/mcp").strip()
VIATOR_USER_AGENT = os.getenv("VIATOR_USER_AGENT", "curl/8.5.0").strip()


def build_default_headers() -> dict[str, str]:
    return {"User-Agent": VIATOR_USER_AGENT}
