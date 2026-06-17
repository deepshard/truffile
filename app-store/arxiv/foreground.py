from __future__ import annotations

import inspect
from typing import Any
from urllib.parse import quote, unquote

from mcp.types import CallToolResult, TextContent
from truffile.app_runtime import ForegroundApp, ToolSpec, resource_link
from truffile.app_runtime.icons import phosphor_icon_url

import arxiv_tools
from tools import TOOLS as _TOOL_SPECS, ToolDefinition



def _make_tool_spec(entry: ToolDefinition) -> ToolSpec:
    supported = set(inspect.signature(ToolSpec).parameters)
    kwargs: dict[str, Any] = {
        "name": entry.name,
        "title": entry.title,
        "description": entry.description,
        "icon": phosphor_icon_url(entry.icon),
        "annotations": dict(entry.annotations),
    }
    if "structured_output" in supported:
        kwargs["structured_output"] = False
    if "readonly" in supported:
        kwargs["readonly"] = bool(entry.annotations.get("readOnlyHint"))
    return ToolSpec(**kwargs)


class ArxivForegroundApp(ForegroundApp):
    def __init__(self) -> None:
        super().__init__("arxiv", logger_name="arxiv.foreground")
        self._register_tools()
        self._register_resources()
        self._register_prompts()

    def _register_tools(self) -> None:
        specs = {entry.name: _make_tool_spec(entry) for entry in _TOOL_SPECS}

        @self.tool(specs["search_papers"])
        async def search_papers_tool(
            query: str,
            max_results: int = 10,
            date_from: str | None = None,
            date_to: str | None = None,
            categories: list[str] | None = None,
            sort_by: str = "relevance",
            include_abstracts: bool = False,
        ) -> CallToolResult:
            return _format_arxiv_result(
                "search_papers",
                await arxiv_tools.search_papers(
                query=query,
                max_results=max_results,
                date_from=date_from,
                date_to=date_to,
                categories=categories,
                sort_by=sort_by,
                include_abstracts=include_abstracts,
                ),
            )

        @self.tool(specs["download_paper"])
        async def download_paper_tool(
            paper_id: str,
            check_status: bool = False,
        ) -> CallToolResult:
            return _format_arxiv_result(
                "download_paper",
                await arxiv_tools.download_paper(
                paper_id=paper_id,
                check_status=check_status,
                ),
            )

        @self.tool(specs["check_paper_status"])
        async def check_paper_status_tool(paper_id: str) -> CallToolResult:
            return _format_arxiv_result("check_paper_status", await arxiv_tools.check_paper_status(paper_id=paper_id))

        @self.tool(specs["list_papers"])
        async def list_papers_tool(include_abstracts: bool = False) -> CallToolResult:
            return _format_arxiv_result("list_papers", await arxiv_tools.list_papers(include_abstracts=include_abstracts))

        @self.tool(specs["read_paper"])
        async def read_paper_tool(
            paper_id: str,
            max_chars: int | None = None,
            offset: int = 0,
            section: str | None = None,
        ) -> CallToolResult:
            return _format_arxiv_result(
                "read_paper",
                await arxiv_tools.read_paper(
                paper_id=paper_id,
                max_chars=max_chars,
                offset=offset,
                section=section,
                ),
            )

        for entry in _TOOL_SPECS:
            tool = self._mcp._tool_manager.get_tool(entry.name)
            metadata = getattr(tool, "fn_metadata", None)
            if metadata is not None:
                metadata.output_schema = None
                metadata.output_model = None
                metadata.wrap_output = False

    def _register_resources(self) -> None:
        @self.resource(
            "arxiv://paper/{paper_id}/markdown",
            name="arxiv_paper_markdown",
            title="arXiv Paper Markdown",
            description="Full converted markdown text for a downloaded arXiv paper.",
            mime_type="text/markdown",
        )
        async def arxiv_paper_markdown(paper_id: str) -> str:
            decoded_id = unquote(paper_id)
            payload = await arxiv_tools.read_paper(paper_id=decoded_id)
            if payload.get("status") != "success":
                raise RuntimeError(str(payload.get("message") or f"Paper {decoded_id} is not available"))
            return str(payload.get("content") or "")

    def _register_prompts(self) -> None:
        @self.prompt(
            "deep-paper-analysis",
            description="Generate a structured deep analysis instruction set for a paper ID.",
        )
        async def deep_paper_analysis_prompt(paper_id: str) -> list[dict[str, str]]:
            return [{"role": "user", "content": arxiv_tools.build_deep_analysis_prompt(paper_id)}]


def _text_result(text: str, *, structured: dict[str, Any] | None = None, is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text.strip())],
        structuredContent=structured,
        isError=is_error,
    )


def _format_arxiv_result(tool_name: str, payload: dict[str, Any]) -> CallToolResult:
    status = str(payload.get("status") or "").strip().lower()
    is_error = status in {"error", "failed", "rate_limited", "not_found"}
    if tool_name in {"search_papers", "list_papers"}:
        return _format_papers_result(tool_name, payload, is_error=is_error)
    if tool_name == "read_paper":
        return _format_read_paper_result(payload, is_error=is_error)
    return _format_status_result(tool_name, payload, is_error=is_error)


def _format_papers_result(tool_name: str, payload: dict[str, Any], *, is_error: bool) -> CallToolResult:
    if is_error:
        return _format_status_result(tool_name, payload, is_error=True)
    papers = payload.get("papers") if isinstance(payload.get("papers"), list) else []
    title = "arXiv search results" if tool_name == "search_papers" else "Stored arXiv papers"
    total = payload.get("total_results", payload.get("total_papers", len(papers)))
    lines = [f"### {title}", f"{total} paper{'s' if total != 1 else ''}."]
    refs: list[dict[str, Any]] = []
    for index, paper in enumerate(papers[:20], start=1):
        if not isinstance(paper, dict):
            continue
        paper_id = str(paper.get("paper_id") or "").strip()
        title_text = str(paper.get("title") or "Untitled").replace("\n", " ").strip()
        authors = paper.get("authors") if isinstance(paper.get("authors"), list) else []
        authors_text = ", ".join(str(author) for author in authors[:3])
        if len(authors) > 3:
            authors_text += ", et al."
        categories = paper.get("categories") if isinstance(paper.get("categories"), list) else []
        category_text = ", ".join(str(cat) for cat in categories[:3])
        date = str(paper.get("published") or paper.get("updated") or "").split("T", 1)[0]
        details = " | ".join(part for part in (paper_id, authors_text, category_text, date) if part)
        lines.append(f"- [{index}] {title_text}" + (f" | {details}" if details else ""))
        abstract = str(paper.get("abstract") or "").replace("\n", " ").strip()
        if abstract:
            lines.append(f"  {abstract[:500].rstrip()}" + ("..." if len(abstract) > 500 else ""))
        ref = {"ref": index}
        for key in ("paper_id", "title", "url", "pdf_url", "resource_uri", "path"):
            value = paper.get(key)
            if value not in (None, ""):
                ref[key] = value
        refs.append(ref)
    if len(papers) > 20:
        lines.append(f"{len(papers) - 20} more paper refs omitted; narrow the query or increase pagination in the underlying tool when available.")
    structured = {"papers": refs, "total": total}
    if len(papers) > 20:
        structured["omitted_count"] = len(papers) - 20
        structured["more_available"] = True
    return _text_result("\n".join(lines), structured=structured)


def _format_read_paper_result(payload: dict[str, Any], *, is_error: bool) -> CallToolResult:
    paper_id = str(payload.get("paper_id") or "").strip()
    if is_error:
        return _format_status_result("read_paper", payload, is_error=True)
    content = str(payload.get("content") or "")
    pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
    section = payload.get("section") if isinstance(payload.get("section"), dict) else {}
    header = f"### arXiv paper {paper_id}" if paper_id else "### arXiv paper"
    lines = [header, content.strip()]
    if pagination:
        footer = (
            f"Offset {pagination.get('offset', 0)}, returned {pagination.get('returned_chars', len(content))} "
            f"of {pagination.get('total_chars', len(content))} chars."
        )
        if pagination.get("truncated") and pagination.get("next_offset") is not None:
            footer += f" More available: call read_paper with paper_id={paper_id!r}, offset={pagination['next_offset']}."
        lines.append(footer)
    structured = {
        key: value
        for key, value in payload.items()
        if key in {"paper_id", "path", "resource_uri", "exists"}
    }
    if pagination:
        structured["pagination"] = pagination
    if section:
        structured["section"] = section
    result = _text_result("\n\n".join(part for part in lines if part), structured=structured)
    _append_paper_resource_link(result, paper_id, payload)
    return result


def _format_status_result(tool_name: str, payload: dict[str, Any], *, is_error: bool) -> CallToolResult:
    paper_id = str(payload.get("paper_id") or "").strip()
    status = str(payload.get("status") or ("error" if is_error else "ok"))
    message = str(payload.get("message") or f"{tool_name} {status}")
    lines = [f"arXiv {tool_name}: {message}"]
    if paper_id:
        lines.append(f"paper_id={paper_id}")
    next_action = payload.get("next_action") or payload.get("next_step")
    if next_action:
        lines.append(f"Next step: {next_action}")
    structured = {
        key: value
        for key, value in payload.items()
        if key
        in {
            "paper_id",
            "path",
            "resource_uri",
            "exists",
            "started_at",
            "completed_at",
            "retry_after_seconds",
            "next_action",
            "section",
        }
        and value not in (None, "", [], {})
    }
    if status and status not in {"success"}:
        structured["state"] = status
    result = _text_result("\n".join(lines), structured=structured or None, is_error=is_error)
    if not is_error:
        _append_paper_resource_link(result, paper_id, payload)
    return result


def _paper_resource_uri(paper_id: str) -> str:
    return f"arxiv://paper/{quote(paper_id, safe='')}/markdown"


def _append_paper_resource_link(result: CallToolResult, paper_id: str, payload: dict[str, Any]) -> None:
    if not paper_id or not payload.get("exists"):
        return
    uri = _paper_resource_uri(paper_id)
    size = None
    try:
        path = str(payload.get("path") or "")
        if path:
            from pathlib import Path

            size = Path(path).stat().st_size
    except OSError:
        size = None
    result.content.append(
        resource_link(
            uri,
            name=f"{paper_id}.md",
            mime_type="text/markdown",
            description=f"Full converted markdown for arXiv paper {paper_id}",
            size=size,
        )
    )


app = ArxivForegroundApp()


if __name__ == "__main__":
    app.run()
