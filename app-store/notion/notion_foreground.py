from __future__ import annotations

import argparse
import atexit
import logging
import os
import sys
from typing import Any

from truffile.app_runtime.errors import ErrorReporter

from auth import NotionAuth
from config import MCP_HOST, MCP_PORT, NOTION_MCP_BASE, build_default_headers
from notion_client import NotionMcpClient
from remote_mcp_compat import load_remote_mcp

RemoteMcpProxyServer = load_remote_mcp().RemoteMcpProxyServer
USER_INFO_RESOURCE_URI = "truffle://user-info"

LOGGER = logging.getLogger("notion.foreground")
LOGGER.setLevel(logging.INFO)
_TITLE_OVERRIDES = {"api": "API", "id": "ID", "mcp": "MCP", "url": "URL"}


def _tool_title_from_name(name: str) -> str:
    words = []
    for part in name.replace("-", "_").split("_"):
        if not part:
            continue
        words.append(_TITLE_OVERRIDES.get(part.lower(), part.capitalize()))
    return " ".join(words) or name


def _infer_tool_annotations(name: str) -> dict[str, bool]:
    lowered = name.lower()
    destructive_words = ("delete", "remove", "archive", "trash")
    read_prefixes = ("get_", "list_", "search_", "fetch_", "read_", "query_", "check_")
    mutating_words = ("create", "update", "edit", "patch", "append", "add", "set")
    if any(word in lowered for word in destructive_words):
        return {"readOnlyHint": False, "destructiveHint": True}
    if lowered.startswith(read_prefixes) or lowered in {"notion_fetch", "notion_search"}:
        return {"readOnlyHint": True, "destructiveHint": False}
    if any(word in lowered for word in mutating_words):
        return {"readOnlyHint": False, "destructiveHint": False}
    return {"readOnlyHint": False, "destructiveHint": False}


def _enrich_tool_metadata(tool: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(tool)
    name = str(enriched.get("name", "") or "")
    enriched.setdefault("title", _tool_title_from_name(name))
    annotations = enriched.get("annotations")
    if not isinstance(annotations, dict):
        annotations = {}
    inferred = _infer_tool_annotations(name)
    annotations.setdefault("readOnlyHint", inferred["readOnlyHint"])
    annotations.setdefault("destructiveHint", inferred["destructiveHint"])
    enriched["annotations"] = annotations
    return enriched


class _StubNotionMcpClient:
    def verify(self) -> tuple[bool, str]:
        return True, "Notion OAuth token verified. workspace=Testing tools=3"

    def list_tools(self) -> list[dict[str, Any]]:
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

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"stub:{name}"}],
            "structuredContent": {"name": name, "arguments": arguments},
            "isError": False,
        }

    def list_resources(self) -> dict[str, Any]:
        return {
            "resources": [
                {
                    "uri": USER_INFO_RESOURCE_URI,
                    "name": "user_info",
                    "title": "User Info",
                    "description": "Profile of the authed Notion workspace.",
                    "mimeType": "text/markdown",
                }
            ]
        }

    def read_resource(self, uri: str) -> dict[str, Any]:
        if uri != USER_INFO_RESOURCE_URI:
            raise RuntimeError(f"Notion resource not found: {uri}")
        return {
            "contents": [
                {
                    "uri": USER_INFO_RESOURCE_URI,
                    "mimeType": "text/markdown",
                    "text": "# Notion\nWorkspace: Testing\nMore: use notion_search / notion_fetch / notion_get_users / notion_get_teams.",
                }
            ]
        }

    def close(self) -> None:
        return None


class NotionForegroundApp:
    def __init__(self) -> None:
        self.name = "notion"
        self.logger = LOGGER
        self._error_reporter = ErrorReporter(logger=self.logger, app_name="notion")
        self._auth: NotionAuth | None = None
        self._client: NotionMcpClient | None = None

    def get_auth(self) -> NotionAuth:
        if self._auth is None:
            self._auth = NotionAuth()
        return self._auth

    def set_auth_for_test(self, auth: NotionAuth) -> None:
        self.reset_for_test()
        self._auth = auth

    def build_client(self) -> NotionMcpClient:
        if os.getenv("APP_STORE_USE_TEST_STUBS") == "1":
            return _StubNotionMcpClient()  # type: ignore[return-value]
        return NotionMcpClient(
            remote_url=NOTION_MCP_BASE,
            auth=self.get_auth(),
            default_headers=build_default_headers(),
        )

    def get_client(self) -> NotionMcpClient:
        if self._client is None:
            self._client = self.build_client()
        return self._client

    def set_client(self, client: NotionMcpClient) -> None:
        self.reset_for_test()
        self._client = client

    def reset_for_test(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                self.logger.exception("Failed closing Notion MCP client")
        self._client = None
        self._auth = None

    def cleanup(self) -> None:
        self.reset_for_test()

    def logger_names(self) -> list[str]:
        return [self.logger.name]

    def list_tools(self) -> list[dict[str, Any]]:
        client = self.get_client()
        if hasattr(client, "list_mcp_tools"):
            tools = client.list_mcp_tools()
        else:
            tools = client.list_tools()
        return [_enrich_tool_metadata(tool) for tool in tools if isinstance(tool, dict)]

    def list_prompts(self) -> list[dict[str, str]]:
        return []

    async def invoke_tool(self, name: str, **arguments: Any) -> Any:
        try:
            return self.get_client().call_tool(name, arguments)
        except Exception as exc:
            await self._error_reporter.report_foreground_exception(exc, tool_name=name)
            raise

    def verify(self) -> tuple[bool, str]:
        client = self.build_client()
        try:
            ok, message = client.verify()
        finally:
            client.close()
        return ok, message

    def run(self) -> None:
        client = self.build_client()
        LOGGER.info("Starting Notion MCP proxy on %s:%d -> %s", MCP_HOST, MCP_PORT, client.remote_url)
        try:
            RemoteMcpProxyServer(client=client, host=MCP_HOST, port=MCP_PORT).serve_forever()
        finally:
            LOGGER.info("Notion MCP proxy stopped")


app = NotionForegroundApp()
atexit.register(app.cleanup)


def set_client(client: NotionMcpClient) -> None:
    app.set_client(client)


def set_auth_for_test(auth: NotionAuth) -> None:
    app.set_auth_for_test(auth)


def reset_for_test() -> None:
    app.reset_for_test()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Notion foreground wrapper")
    parser.add_argument("--verify", action="store_true", help="Verify installed OAuth token and MCP binary")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        if args.verify:
            ok, message = app.verify()
            print(message, flush=True)
            return 0 if ok else 1
        app.run()
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
