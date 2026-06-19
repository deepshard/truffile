from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


DEFAULT_MCP_PATH = "/api/mcp"


class HomeAssistantConfigError(ValueError):
    pass


def normalize_base_url(raw_url: str) -> str:
    url = raw_url.strip().rstrip("/")
    if not url:
        raise HomeAssistantConfigError("HOME_ASSISTANT_BASE_URL is required.")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HomeAssistantConfigError(
            "HOME_ASSISTANT_BASE_URL must be an http or https URL, for example https://homeassistant.local:8123."
        )

    return url


def normalize_mcp_path(raw_path: str | None) -> str:
    path = (raw_path or DEFAULT_MCP_PATH).strip()
    if not path:
        return DEFAULT_MCP_PATH
    if not path.startswith("/"):
        path = f"/{path}"
    return path


@dataclass(frozen=True, slots=True)
class HomeAssistantConfig:
    base_url: str
    token: str
    mcp_path: str = DEFAULT_MCP_PATH

    @property
    def mcp_url(self) -> str:
        return f"{self.base_url}{self.mcp_path}"

    @property
    def rest_api_url(self) -> str:
        return f"{self.base_url}/api/"


def load_config() -> HomeAssistantConfig:
    base_url = normalize_base_url(os.environ.get("HOME_ASSISTANT_BASE_URL", ""))
    token = os.environ.get("HOME_ASSISTANT_TOKEN", "").strip()
    if not token:
        raise HomeAssistantConfigError("HOME_ASSISTANT_TOKEN is required.")

    return HomeAssistantConfig(
        base_url=base_url,
        token=token,
        mcp_path=normalize_mcp_path(os.environ.get("HOME_ASSISTANT_MCP_PATH")),
    )
