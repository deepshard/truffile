from __future__ import annotations

import logging
from typing import Any

from app_runtime.mcp import create_mcp_server, run_mcp_server

from arxiv_tools import (
    build_deep_analysis_prompt,
    download_paper,
    list_papers,
    read_paper,
    search_papers,
)
from mcp.types import Icon

logger = logging.getLogger("arxiv.foreground")
logger.setLevel(logging.INFO)

mcp = create_mcp_server("arxiv")


@mcp.tool(
    "search_papers",
    description=(
        "Search arXiv papers with optional date/category filters. "
        "Use quoted phrases for exact matches (for example: \"multi-agent systems\") "
        "and categories for precision (for example: cs.AI, cs.LG, cs.CL)."
    ),
    icons=[Icon(src="https://raw.githubusercontent.com/phosphor-icons/core/main/assets/regular/magnifying-glass.svg")],
)
async def tool_search_papers(
    query: str,
    max_results: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
    categories: list[str] | None = None,
    sort_by: str = "relevance",
) -> dict[str, Any]:
    return await search_papers(
        query=query,
        max_results=max_results,
        date_from=date_from,
        date_to=date_to,
        categories=categories,
        sort_by=sort_by,
    )


@mcp.tool(
    "download_paper",
    description=(
        "Download an arXiv paper by ID and convert it to markdown for local reading. "
        "Use check_status=true to poll conversion progress."
    ),
    icons=[Icon(src="https://raw.githubusercontent.com/phosphor-icons/core/main/assets/regular/download-simple.svg")],
)
async def tool_download_paper(
    paper_id: str,
    check_status: bool = False,
) -> dict[str, Any]:
    return await download_paper(paper_id=paper_id, check_status=check_status)


@mcp.tool(
    "list_papers",
    description="List papers currently downloaded to local storage.",
    icons=[Icon(src="https://raw.githubusercontent.com/phosphor-icons/core/main/assets/regular/list.svg")],
)
async def tool_list_papers() -> dict[str, Any]:
    return await list_papers()


@mcp.tool(
    "read_paper",
    description="Read full markdown content for a downloaded paper by arXiv ID.",
    icons=[Icon(src="https://raw.githubusercontent.com/phosphor-icons/core/main/assets/regular/book-open-text.svg")],
)
async def tool_read_paper(paper_id: str) -> dict[str, Any]:
    return await read_paper(paper_id=paper_id)


@mcp.prompt(
    "deep-paper-analysis",
    description="Generate a structured deep analysis instruction set for a paper ID.",
)
async def prompt_deep_paper_analysis(paper_id: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": build_deep_analysis_prompt(paper_id)}]


if __name__ == "__main__":
    run_mcp_server(mcp, logger)
