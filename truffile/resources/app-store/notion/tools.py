"""Static Notion MCP tool metadata for default-app publishing."""

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
    ToolDefinition(
        name="notion_search",
        title="Notion Search",
        description="Search across Notion workspace content and connected sources when available.",
        icon="magnifying-glass",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_fetch",
        title="Notion Fetch",
        description="Fetch Notion pages, databases, or data sources by URL or ID.",
        icon="book-open-text",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_create_pages",
        title="Notion Create Pages",
        description="Create one or more Notion pages with properties, content, icons, covers, and templates.",
        icon="file-plus",
        annotations={"readOnlyHint": False, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_update_page",
        title="Notion Update Page",
        description="Update a Notion page's properties, content, icon, cover, or applied template.",
        icon="pencil-simple",
        annotations={"readOnlyHint": False, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_move_pages",
        title="Notion Move Pages",
        description="Move one or more Notion pages or databases to a new parent.",
        icon="arrows-out-cardinal",
        annotations={"readOnlyHint": False, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_duplicate_page",
        title="Notion Duplicate Page",
        description="Duplicate a Notion page within the connected workspace.",
        icon="copy",
        annotations={"readOnlyHint": False, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_create_database",
        title="Notion Create Database",
        description="Create a Notion database with an initial data source, view, and properties.",
        icon="database",
        annotations={"readOnlyHint": False, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_update_data_source",
        title="Notion Update Data Source",
        description="Update a Notion data source's properties, name, description, or attributes.",
        icon="table",
        annotations={"readOnlyHint": False, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_create_view",
        title="Notion Create View",
        description="Create a view on a Notion database, including table, board, list, calendar, timeline, and gallery views.",
        icon="layout",
        annotations={"readOnlyHint": False, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_update_view",
        title="Notion Update View",
        description="Update a Notion database view's name, filters, sorts, grouping, or display configuration.",
        icon="sliders-horizontal",
        annotations={"readOnlyHint": False, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_query_data_sources",
        title="Notion Query Data Sources",
        description="Query across Notion data sources with structured summaries, grouping, and filters.",
        icon="funnel",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_query_database_view",
        title="Notion Query Database View",
        description="Query a Notion database using an existing view's filters and sorts.",
        icon="table",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_create_comment",
        title="Notion Create Comment",
        description="Add a page-level, block-level, inline, or reply comment in Notion.",
        icon="chat-circle-dots",
        annotations={"readOnlyHint": False, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_get_comments",
        title="Notion Get Comments",
        description="List comments and discussions on a Notion page, including resolved threads when available.",
        icon="chats",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_get_teams",
        title="Notion Get Teams",
        description="List teams and teamspaces in the current Notion workspace.",
        icon="users-three",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_get_users",
        title="Notion Get Users",
        description="List users in the connected Notion workspace.",
        icon="address-book",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_get_user",
        title="Notion Get User",
        description="Retrieve Notion user information by ID.",
        icon="user-circle",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="notion_get_self",
        title="Notion Get Self",
        description="Get the connected Notion bot user and workspace information.",
        icon="identification-card",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
