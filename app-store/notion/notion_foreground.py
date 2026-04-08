from __future__ import annotations

import argparse
import atexit
import logging
import os
import sys
from typing import Any



from truffile.app_runtime.errors import AppAuthError, AppRuntimeFailure, ErrorReporter

from auth import NotionAuth
from config import MCP_HOST, MCP_PORT, resolve_binary
from notion_client import ManagedNotionMcpProcessClient, NotionMcpClient, verify_notion_workspace

LOGGER = logging.getLogger("notion.foreground")
LOGGER.setLevel(logging.INFO)


class _StubNotionMcpClient:
    def verify(self) -> tuple[bool, str]:
        return True, "Notion access token verified. workspace=Testing tools=3"

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
        token = self.get_auth().get_access_token()
        if not token:
            raise RuntimeError("Notion access token missing or empty")
        server_bin = resolve_binary()
        return ManagedNotionMcpProcessClient(
            notion_token=token,
            server_bin=server_bin,
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
        return self.get_client().list_tools()

    def list_prompts(self) -> list[dict[str, str]]:
        return []

    async def invoke_tool(self, name: str, **arguments: Any) -> Any:
        try:
            return self.get_client().call_tool(name, arguments)
        except Exception as exc:
            await self._error_reporter.report_foreground_exception(exc, tool_name=name)
            raise

    def verify(self) -> tuple[bool, str]:
        token = self.get_auth().get_access_token()
        if not token:
            return False, "Notion access token missing or empty"
        workspace_ok, workspace_message = verify_notion_workspace(token)
        if not workspace_ok:
            return False, workspace_message
        client = self.build_client()
        try:
            ok, message = client.verify()
        finally:
            client.close()
        if not ok:
            return ok, message
        return True, f"Notion access token verified. {workspace_message}. {message}"

    def run(self) -> None:
        token = self.get_auth().get_access_token()
        if not token:
            raise RuntimeError("Notion access token missing or empty")
        server_bin = resolve_binary()
        env = dict(os.environ)
        env["NOTION_TOKEN"] = token
        cmd = [
            server_bin,
            "--transport",
            "http",
            "--port",
            str(MCP_PORT),
            "--disable-auth",
        ]
        LOGGER.info("Starting Notion MCP server on %s:%d", MCP_HOST, MCP_PORT)
        os.execvpe(cmd[0], cmd, env)


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
    parser.add_argument("--verify", action="store_true", help="Verify installed access token and MCP binary")
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
