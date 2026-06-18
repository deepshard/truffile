from __future__ import annotations

import argparse
import atexit
import logging
import os
import sys
from typing import Any

from truffile.app_runtime.errors import ErrorReporter

from auth import TurkishAirlinesAuth
from config import MCP_HOST, MCP_PORT, TURKISH_AIRLINES_MCP_BASE, build_default_headers
from turkish_client import TurkishAirlinesMcpClient
from remote_mcp_compat import load_remote_mcp

RemoteMcpProxyServer = load_remote_mcp().RemoteMcpProxyServer
USER_INFO_RESOURCE_URI = "truffle://user-info"

LOGGER = logging.getLogger("turkish.foreground")
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
    destructive_words = ("delete", "remove", "archive", "trash", "cancel")
    read_prefixes = ("get_", "list_", "search_", "fetch_", "read_", "query_", "check_")
    mutating_words = ("create", "update", "edit", "patch", "append", "add", "set")
    if any(word in lowered for word in destructive_words):
        return {"readOnlyHint": False, "destructiveHint": True}
    if lowered.startswith(read_prefixes):
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


class _StubTurkishAirlinesMcpClient:
    def verify(self) -> tuple[bool, str]:
        return True, "Turkish Airlines OAuth token verified. Tools=8"

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "search_flights", "description": "Search for available flights.", "inputSchema": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "date": {"type": "string"}}}},
            {"name": "flight_status", "description": "Get real-time flight status.", "inputSchema": {"type": "object", "properties": {"flight_number": {"type": "string"}}}},
            {"name": "booking_details", "description": "Retrieve booking details.", "inputSchema": {"type": "object", "properties": {"pnr": {"type": "string"}, "surname": {"type": "string"}}}},
            {"name": "check_in", "description": "Check in for a flight.", "inputSchema": {"type": "object", "properties": {"pnr": {"type": "string"}, "surname": {"type": "string"}}}},
            {"name": "miles_profile", "description": "Get Miles&Smiles account info.", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "miles_balance", "description": "Check miles balance.", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "miles_history", "description": "Get miles transaction history.", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "cancel_booking", "description": "Cancel or modify a booking.", "inputSchema": {"type": "object", "properties": {"pnr": {"type": "string"}, "surname": {"type": "string"}}}},
        ]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": f"stub:{name}"}], "structuredContent": {"name": name, "arguments": arguments}, "isError": False}

    def list_resources(self) -> dict[str, Any]:
        return {"resources": [{"uri": USER_INFO_RESOURCE_URI, "name": "user_info", "title": "User Info", "description": "Profile of the authed Turkish Airlines account.", "mimeType": "text/markdown"}]}

    def read_resource(self, uri: str) -> dict[str, Any]:
        if uri != USER_INFO_RESOURCE_URI:
            raise RuntimeError(f"Turkish Airlines resource not found: {uri}")
        return {"contents": [{"uri": USER_INFO_RESOURCE_URI, "mimeType": "text/markdown", "text": "# Turkish Airlines\nConnected via MCP\nTools: search_flights, flight_status, booking_details, check_in, miles_profile, miles_balance, miles_history, cancel_booking."}]}

    def close(self) -> None:
        return None


class TurkishAirlinesForegroundApp:
    def __init__(self) -> None:
        self.name = "turkish-airlines"
        self.logger = LOGGER
        self._error_reporter = ErrorReporter(logger=self.logger, app_name="turkish-airlines")
        self._auth: TurkishAirlinesAuth | None = None
        self._client: TurkishAirlinesMcpClient | None = None

    def get_auth(self) -> TurkishAirlinesAuth:
        if self._auth is None:
            self._auth = TurkishAirlinesAuth()
        return self._auth

    def set_auth_for_test(self, auth: TurkishAirlinesAuth) -> None:
        self.reset_for_test()
        self._auth = auth

    def build_client(self) -> TurkishAirlinesMcpClient:
        if os.getenv("APP_STORE_USE_TEST_STUBS") == "1":
            return _StubTurkishAirlinesMcpClient()  # type: ignore[return-value]
        return TurkishAirlinesMcpClient(
            remote_url=TURKISH_AIRLINES_MCP_BASE,
            auth=self.get_auth(),
            default_headers=build_default_headers(),
        )

    def get_client(self) -> TurkishAirlinesMcpClient:
        if self._client is None:
            self._client = self.build_client()
        return self._client

    def set_client(self, client: TurkishAirlinesMcpClient) -> None:
        self.reset_for_test()
        self._client = client

    def reset_for_test(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                self.logger.exception("Failed closing Turkish Airlines MCP client")
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
        LOGGER.info("Starting Turkish Airlines MCP proxy on %s:%d -> %s", MCP_HOST, MCP_PORT, client.remote_url)
        try:
            RemoteMcpProxyServer(client=client, host=MCP_HOST, port=MCP_PORT).serve_forever()
        finally:
            LOGGER.info("Turkish Airlines MCP proxy stopped")


app = TurkishAirlinesForegroundApp()
atexit.register(app.cleanup)


def set_client(client: TurkishAirlinesMcpClient) -> None:
    app.set_client(client)


def set_auth_for_test(auth: TurkishAirlinesAuth) -> None:
    app.set_auth_for_test(auth)


def reset_for_test() -> None:
    app.reset_for_test()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Turkish Airlines foreground wrapper")
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