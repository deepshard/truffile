from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any
from urllib import parse as urlparse

from truffile.app_runtime.icons import phosphor_icon_url

EXA_MCP_BASE = os.getenv("EXA_MCP_BASE", "https://mcp.exa.ai/mcp")
DEFAULT_EXA_TOOLS = (
    "web_search_exa,web_search_advanced_exa,get_code_context_exa,"
    "crawling_exa,company_research_exa,people_search_exa,"
    "deep_researcher_start,deep_researcher_check"
)


@dataclass(frozen=True, slots=True)
class ExaToolDefinition:
    name: str
    description: str
    icon_name: str


def _tool_description(summary: str, *, params: list[str], example: str) -> str:
    params_block = "\n".join(f"- {line}" for line in params)
    return f"{summary}\n\nParameters:\n{params_block}\n\nExample:\n{example}"


TOOL_DEFINITIONS: dict[str, ExaToolDefinition] = {
    "web_search_exa": ExaToolDefinition(
        name="web_search_exa",
        description=_tool_description(
            "Search the web for current information. Use this for straightforward lookups, recent facts, and finding relevant pages on a topic. Describe the ideal page rather than using bare keywords.",
            params=[
                "query (required): natural language search query describing the ideal page.",
                "numResults (optional): integer 1-100, number of results to return; default 8.",
                "type (optional): 'auto' (balanced, default) or 'fast' (quick results).",
                "category (optional): filter to 'company', 'research paper', 'news', 'personal site', 'people', or 'financial report'.",
                "freshness (optional): recency filter — '24h', 'week', 'month', 'year', or 'any'. Only set when recency matters.",
                "includeDomains (optional): list of domain strings to restrict results to, e.g. ['arxiv.org'].",
            ],
            example='web_search_exa(query="blog post comparing React and Vue performance", numResults=5)',
        ),
        icon_name="globe",
    ),
    "web_search_advanced_exa": ExaToolDefinition(
        name="web_search_advanced_exa",
        description=_tool_description(
            "Advanced web search with full control over filters, domains, date ranges, and content options. Use when you need date filtering, domain restrictions, text inclusion/exclusion, or neural search.",
            params=[
                "query (required): search query string.",
                "numResults (optional): integer 1-100, number of results; default 10.",
                "type (optional): 'auto' (default), 'fast', or 'neural' (semantic search).",
                "category (optional): 'company', 'research paper', 'news', 'pdf', 'github', 'personal site', 'people', or 'financial report'.",
                "includeDomains (optional): list of allowed domain strings, e.g. ['openai.com', 'anthropic.com'].",
                "excludeDomains (optional): list of blocked domain strings.",
                "startPublishedDate (optional): ISO 8601 date lower bound, e.g. '2026-01-01'.",
                "endPublishedDate (optional): ISO 8601 date upper bound.",
                "startCrawlDate (optional): ISO 8601 date — only results crawled after this date.",
                "endCrawlDate (optional): ISO 8601 date — only results crawled before this date.",
                "includeText (optional): list of strings — only include results containing ALL of these.",
                "excludeText (optional): list of strings — exclude results containing ANY of these.",
                "enableHighlights (optional): boolean to enable highlight extraction.",
                "enableSummary (optional): boolean to enable summary generation.",
                "subpages (optional): integer 1-10, number of subpages to crawl per result.",
            ],
            example='web_search_advanced_exa(query="AI safety policy", includeDomains=["openai.com","anthropic.com"], startPublishedDate="2026-01-01", numResults=5)',
        ),
        icon_name="globe-stand",
    ),
    "get_code_context_exa": ExaToolDefinition(
        name="get_code_context_exa",
        description=_tool_description(
            "Search technical sources for code examples, documentation, and programming solutions. Use for library usage, API details, and coding research. Describe what you need specifically.",
            params=[
                "query (required): technical search string, e.g. 'Python requests library POST with JSON body'.",
                "numResults (optional): integer 1-20, number of results; default 8.",
            ],
            example='get_code_context_exa(query="FastAPI background tasks example", numResults=5)',
        ),
        icon_name="terminal",
    ),
    "crawling_exa": ExaToolDefinition(
        name="crawling_exa",
        description=_tool_description(
            "Fetch and read full page content as clean markdown from one or more URLs. Use after web_search_exa when highlights are insufficient, or to read any known URL. Batch multiple URLs in one call.",
            params=[
                "urls (required): list of URL strings to crawl, e.g. ['https://example.com/page'].",
                "maxCharacters (optional): integer cap on extracted text per page; default 3000.",
                "maxAgeHours (optional): max age of cached content in hours. 0 = always fetch fresh.",
                "subpages (optional): integer number of linked subpages to also crawl from each URL.",
                "subpageTarget (optional): keywords string to prioritize when selecting subpages.",
            ],
            example='crawling_exa(urls=["https://openai.com/index/gpt-4-1/"], maxCharacters=12000)',
        ),
        icon_name="browsers",
    ),
    "company_research_exa": ExaToolDefinition(
        name="company_research_exa",
        description=_tool_description(
            "Research a company to get business information, news, financials, and insights. (Deprecated — web_search_advanced_exa is preferred.)",
            params=[
                "companyName (required): the name of the company to research.",
                "numResults (optional): integer number of results; default 3.",
            ],
            example='company_research_exa(companyName="Stripe", numResults=3)',
        ),
        icon_name="building-office",
    ),
    "people_search_exa": ExaToolDefinition(
        name="people_search_exa",
        description=_tool_description(
            "Find people and their professional profiles. (Deprecated — web_search_advanced_exa is preferred.)",
            params=[
                "query (required): person name or person-focused search query.",
                "numResults (optional): integer number of profile results; default 5.",
            ],
            example='people_search_exa(query="Dario Amodei Anthropic CEO", numResults=3)',
        ),
        icon_name="address-book",
    ),
    "deep_researcher_start": ExaToolDefinition(
        name="deep_researcher_start",
        description=_tool_description(
            "Start an asynchronous deep research job that searches, reads, and writes a detailed report. Takes 15 seconds to 2 minutes. After calling, poll with deep_researcher_check using the returned researchId. (Deprecated.)",
            params=[
                "instructions (required): detailed research question or instructions for the AI researcher.",
                "model (required): 'exa-research-fast' (~15s, default), 'exa-research' (15-45s), or 'exa-research-pro' (45s-3min, most comprehensive).",
                "outputSchema (optional): JSON Schema object for structured output.",
            ],
            example='deep_researcher_start(instructions="Compare the latest AI coding agents on autonomy, safety, and pricing", model="exa-research-fast")',
        ),
        icon_name="binoculars",
    ),
    "deep_researcher_check": ExaToolDefinition(
        name="deep_researcher_check",
        description=_tool_description(
            "Check status and retrieve results from a deep research task started with deep_researcher_start. Keep polling until status is 'completed'.",
            params=[
                "researchId (required): the research ID string returned by deep_researcher_start.",
            ],
            example='deep_researcher_check(researchId="r_01kmm0ny9pfx44ed2kgrknfvz2")',
        ),
        icon_name="check",
    ),
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
        description=f"Call the Exa MCP tool '{name}'.",
        icon_name="sparkle",
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
