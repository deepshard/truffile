from __future__ import annotations

from typing import Any

from truffile.app_runtime import ForegroundApp, ToolSpec, phosphor_icon_url

import arxiv_tools


class ArxivForegroundApp(ForegroundApp):
    def __init__(self) -> None:
        super().__init__("arxiv", logger_name="arxiv.foreground")
        self._register_tools()
        self._register_prompts()

    def _register_tools(self) -> None:
        @self.tool(
            ToolSpec(
                name="search_papers",
                description=(
                "Search arXiv papers with optional date/category filters. "
                "Use quoted phrases for exact matches (for example: \"multi-agent systems\") "
                "and categories for precision (for example: cs.AI, cs.LG, cs.CL)."
                ),
                icon=phosphor_icon_url("magnifying-glass"),
            )
        )
        async def search_papers_tool(
            query: str,
            max_results: int = 10,
            date_from: str | None = None,
            date_to: str | None = None,
            categories: list[str] | None = None,
            sort_by: str = "relevance",
        ) -> dict[str, Any]:
            return await arxiv_tools.search_papers(
                query=query,
                max_results=max_results,
                date_from=date_from,
                date_to=date_to,
                categories=categories,
                sort_by=sort_by,
            )

        @self.tool(
            ToolSpec(
                name="download_paper",
                description=(
                "Download an arXiv paper by ID and convert it to markdown for local reading. "
                "Use check_status=true to poll conversion progress."
                ),
                icon=phosphor_icon_url("download-simple"),
            )
        )
        async def download_paper_tool(
            paper_id: str,
            check_status: bool = False,
        ) -> dict[str, Any]:
            return await arxiv_tools.download_paper(
                paper_id=paper_id,
                check_status=check_status,
            )

        @self.tool(
            ToolSpec(
                name="list_papers",
                description="List papers currently downloaded to local storage.",
                icon=phosphor_icon_url("list"),
            )
        )
        async def list_papers_tool() -> dict[str, Any]:
            return await arxiv_tools.list_papers()

        @self.tool(
            ToolSpec(
                name="read_paper",
                description="Read full markdown content for a downloaded paper by arXiv ID.",
                icon=phosphor_icon_url("book-open-text"),
            )
        )
        async def read_paper_tool(paper_id: str) -> dict[str, Any]:
            return await arxiv_tools.read_paper(paper_id=paper_id)

    def _register_prompts(self) -> None:
        @self.prompt(
            "deep-paper-analysis",
            description="Generate a structured deep analysis instruction set for a paper ID.",
        )
        async def deep_paper_analysis_prompt(paper_id: str) -> list[dict[str, str]]:
            return [{"role": "user", "content": arxiv_tools.build_deep_analysis_prompt(paper_id)}]


app = ArxivForegroundApp()


if __name__ == "__main__":
    app.run()
