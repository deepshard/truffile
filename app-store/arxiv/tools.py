"""Canonical foreground tool metadata for runtime registration and default-app publishing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    title: str
    description: str
    icon: str
    annotations: dict[str, bool]


TOOLS = [
 ToolDefinition(**{'name': 'search_papers',
 'title': 'Search Papers',
 'description': 'Search arXiv papers by topic, quoted phrase, author/title query, date range, and category filter. Use '
                'for literature discovery, recent paper search, and finding arXiv IDs to download or read later. '
                'Returns compact paper metadata with paper IDs, titles, authors, categories, published/updated dates, '
                'and one arXiv URL. Set include_abstracts=true only when abstracts are needed.',
 'icon': 'magnifying-glass',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'download_paper',
 'title': 'Download Paper',
 'description': "Download an arXiv paper PDF by arXiv ID into this app's local storage and convert it to markdown for "
                'later reading. This starts or reuses local cache work; use check_paper_status to poll conversion '
                'status. check_status remains accepted only as a backward-compatible status check. Returns status, '
                'paper_id, whether the converted paper exists, local markdown path, and resource_uri for MCP resource reads.',
 'icon': 'download-simple',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'check_paper_status',
 'title': 'Check Paper Status',
 'description': 'Check local download/conversion status for an arXiv paper ID without starting a new download. Use '
                'after download_paper returns status=converting. Returns status, paper_id, existence, path, resource_uri, and '
                'conversion timestamps only when a conversion is in progress.',
 'icon': 'clock-countdown',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'list_papers',
 'title': 'List Papers',
 'description': 'List arXiv papers currently downloaded in local app storage. Use before reading or summarizing a '
                'cached paper. Returns compact cached paper metadata, local markdown paths, and resource_uri values. Set '
                'include_abstracts=true only when abstracts are needed.',
 'icon': 'list',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'read_paper',
 'title': 'Read Paper',
 'description': 'Read markdown text for a downloaded arXiv paper by arXiv ID. Supports max_chars and offset '
                'pagination, plus section selection by markdown/page heading when available. Use after download_paper '
                'has completed or when list_papers shows the paper is cached. Returns content, pagination, section '
                'metadata, paper_id, existence, local path, and resource_uri.',
 'icon': 'book-open-text',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}})
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
