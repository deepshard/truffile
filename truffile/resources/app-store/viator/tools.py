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
 ToolDefinition(**{'name': 'search_experiences',
 'title': 'Search Experiences',
 'description': 'Search Viator experiences by destination, dates, traveler context, budget, accessibility needs, and '
                'interests. Returns compact summaries by default with code, title, price, rating, duration, category, '
                'free cancellation, and product URL. Use include_images for image URLs and include_raw only for '
                'debugging raw Viator MCP output.',
 'icon': 'magnifying-glass',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}}),
 ToolDefinition(**{'name': 'get_experience_details',
 'title': 'Get Experience Details',
 'description': 'Get compact details for a Viator experience code returned by search_experiences. Defaults include '
                'code, title, bounded description, rating, reviews count, cancellation flag, product URL, and currency '
                'when available. Use max_chars for description length, include_details for planning fields, '
                'include_reviews for bounded review snippets, include_images for image URL, and include_raw only for '
                'debugging raw Viator MCP output.',
 'icon': 'book-open-text',
 'annotations': {'readOnlyHint': True, 'destructiveHint': False}})
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
