from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any
from urllib import parse as urlparse

from truffile.app_runtime.icons import phosphor_icon_url
from tools import TOOLS_BY_NAME

EXA_MCP_BASE = os.getenv("EXA_MCP_BASE", "https://mcp.exa.ai/mcp")
DEFAULT_EXA_TOOLS = (
    "web_search_exa,web_search_advanced_exa,get_code_context_exa,"
    "crawling_exa,company_research_exa,people_search_exa,"
    "deep_researcher_start,deep_researcher_check"
)


@dataclass(frozen=True, slots=True)
class ExaToolDefinition:
    name: str
    title: str
    description: str
    icon_name: str
    annotations: dict[str, bool]


TOOL_DEFINITIONS: dict[str, ExaToolDefinition] = {
    name: ExaToolDefinition(
        name=tool.name,
        title=tool.title,
        description=tool.description,
        icon_name=tool.icon,
        annotations=dict(tool.annotations),
    )
    for name, tool in TOOLS_BY_NAME.items()
    if name != "check_exa_auth"
}


def parse_tools_csv(raw: str | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for entry in (raw or "").split(","):
        tool = entry.strip()
        if not tool or tool in seen:
            continue
        out.append(tool)
        seen.add(tool)
    return out


def tools_csv(raw: str | None) -> str:
    return ",".join(parse_tools_csv(raw))


def selected_tool_names() -> list[str]:
    return parse_tools_csv(os.getenv("EXA_TOOLS", DEFAULT_EXA_TOOLS))


def tool_definition(name: str) -> ExaToolDefinition:
    definition = TOOL_DEFINITIONS.get(name)
    if definition is not None:
        return definition
    return ExaToolDefinition(
        name=name,
        title=" ".join(part.capitalize() for part in name.replace("-", "_").split("_") if part) or name,
        description=f"Call the Exa MCP tool '{name}'.",
        icon_name="sparkle",
        annotations={"readOnlyHint": False, "destructiveHint": False},
    )


def build_remote_url(*, api_key: str, base_url: str | None = None, tools: str | None = None) -> str:
    params = {"exaApiKey": api_key}
    tools_value = tools_csv(tools if tools is not None else os.getenv("EXA_TOOLS", DEFAULT_EXA_TOOLS))
    if tools_value:
        params["tools"] = tools_value
    return f"{(base_url or EXA_MCP_BASE)}?{urlparse.urlencode(params)}"


def read_api_key() -> str:
    key = os.getenv("EXA_API_KEY", "").strip()
    if not key:
        raise ValueError("Missing EXA_API_KEY")
    return key


def mask_key(raw: str) -> str:
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"


def icon_url_for_tool(name: str) -> str:
    return phosphor_icon_url(tool_definition(name).icon_name)


def sanitize_tool_result(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [sanitize_tool_result(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize_tool_result(item) for key, item in value.items()}
    return str(value)
