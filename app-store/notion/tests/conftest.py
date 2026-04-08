import sys
from pathlib import Path
import types


# add app dir to sys.path for local imports
_app_dir = Path(__file__).resolve().parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

def install_stub_modules() -> None:
    notion_client = types.ModuleType("notion_client")

    def verify_notion_workspace(token: str) -> tuple[bool, str]:
        masked = token[:4] + "..." if token else "none"
        return True, f"workspace=Testing token={masked}"

    class NotionMcpClient:
        def verify(self) -> tuple[bool, str]:
            return True, "Notion MCP verified. tools=3"

        def list_tools(self) -> list[dict[str, object]]:
            return [
                {
                    "name": "notion_fetch",
                    "description": "Fetch a Notion page or database.",
                    "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}},
                },
                {
                    "name": "notion_search",
                    "description": "Search the Notion workspace.",
                    "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
                {
                    "name": "notion_update_page",
                    "description": "Update a Notion page.",
                    "inputSchema": {"type": "object", "properties": {"page_id": {"type": "string"}}},
                },
            ]

        def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
            return {
                "content": [{"type": "text", "text": f"stub:{name}"}],
                "structuredContent": {"name": name, "arguments": arguments},
                "isError": False,
            }

        def close(self) -> None:
            return None

    class ManagedNotionMcpProcessClient(NotionMcpClient):
        def __init__(self, *, notion_token: str, server_bin: str, process_launcher=None, startup_timeout_seconds: float = 15.0):
            del notion_token, server_bin, process_launcher, startup_timeout_seconds

    notion_client.verify_notion_workspace = verify_notion_workspace
    notion_client.NotionMcpClient = NotionMcpClient
    notion_client.ManagedNotionMcpProcessClient = ManagedNotionMcpProcessClient
    sys.modules["notion_client"] = notion_client


install_stub_modules()
