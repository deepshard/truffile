from __future__ import annotations

from dataclasses import replace
import inspect
import json
from typing import Any

from remote_mcp_compat import load_remote_mcp

_remote_mcp = load_remote_mcp()
RemoteMcpClient = _remote_mcp.RemoteMcpClient
RemoteMcpOAuth = _remote_mcp.RemoteMcpOAuth
RemoteMcpTool = _remote_mcp.RemoteMcpTool

USER_INFO_RESOURCE_URI = "truffle://user-info"


def _user_info_resource_entry() -> dict[str, str]:
    return {
        "uri": USER_INFO_RESOURCE_URI,
        "name": "user_info",
        "title": "User Info",
        "description": "Profile of the authed Notion workspace.",
        "mimeType": "text/markdown",
    }


def _with_user_info_resource(result: Any) -> dict[str, Any]:
    payload = dict(result) if isinstance(result, dict) else {"resources": []}
    resources = list(payload.get("resources") or [])
    if not any(isinstance(resource, dict) and resource.get("uri") == USER_INFO_RESOURCE_URI for resource in resources):
        resources.append(_user_info_resource_entry())
    payload["resources"] = resources
    return payload


def _read_user_info_result(text: str) -> dict[str, Any]:
    return {
        "contents": [
            {
                "uri": USER_INFO_RESOURCE_URI,
                "mimeType": "text/markdown",
                "text": text.strip(),
            }
        ]
    }


def _content_text(result: Any) -> str:
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = str(item.get("text") or "").strip()
                    if text:
                        parts.append(text)
            return "\n".join(parts)
    return ""


def _structured(result: Any) -> Any:
    if isinstance(result, dict) and "structuredContent" in result:
        return result["structuredContent"]
    if isinstance(result, dict):
        for key in ("text", "message"):
            value = result.get(key)
            if isinstance(value, str) and value.strip() and value.strip()[0] in "{[":
                try:
                    return json.loads(value)
                except Exception:
                    pass
    text = _content_text(result)
    if text and text[0] in "{[":
        try:
            return json.loads(text)
        except Exception:
            return {}
    return result


def _collect_dicts(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        out.append(value)
        for child in value.values():
            out.extend(_collect_dicts(child))
    elif isinstance(value, list):
        for item in value:
            out.extend(_collect_dicts(item))
    return out


def _first_str(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _is_expired_session_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "session" in text and (
        "invalid or expired" in text
        or "expired session" in text
        or "invalid session" in text
        or ("session token" in text and ("invalid" in text or "expired" in text))
    )


class NotionMcpClient(RemoteMcpClient):
    def __init__(
        self,
        *,
        remote_url: str,
        auth: RemoteMcpOAuth,
        default_headers: dict[str, str] | None = None,
        post_jsonrpc: Any = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "remote_url": remote_url,
            "auth": auth,
            "default_headers": default_headers,
            "app_name": "Notion",
            "post_jsonrpc": post_jsonrpc,
        }
        if "protocol_version" in inspect.signature(RemoteMcpClient.__init__).parameters:
            kwargs["protocol_version"] = "2025-06-18"
        super().__init__(**kwargs)
        self._notion_auth = auth

    def _reset_remote_session(self) -> None:
        self._initialized = False
        self._session_id = None

    @staticmethod
    def _public_tool_name(name: str) -> str:
        return str(name or "").replace("-", "_")

    def _normalize_notion_tools(self, tools: list[RemoteMcpTool]) -> list[RemoteMcpTool]:
        normalized: list[RemoteMcpTool] = []
        self._tool_name_map = {}
        for tool in tools:
            public_name = self._public_tool_name(getattr(tool, "public_name", ""))
            remote_name = str(getattr(tool, "remote_name", public_name) or public_name)
            if public_name != getattr(tool, "public_name", ""):
                tool = replace(tool, public_name=public_name)
            normalized.append(tool)
            self._tool_name_map[public_name] = remote_name
            self._tool_name_map[remote_name] = remote_name
        return normalized

    def list_tools(self) -> list[RemoteMcpTool]:
        try:
            return self._normalize_notion_tools(super().list_tools())
        except Exception as exc:
            if not _is_expired_session_error(exc):
                raise
            self._reset_remote_session()
            return self._normalize_notion_tools(super().list_tools())

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return super().call_tool(name, arguments)
        except Exception as exc:
            if not _is_expired_session_error(exc):
                raise
            self._reset_remote_session()
            return super().call_tool(name, arguments)

    def list_resources(self) -> Any:
        try:
            return _with_user_info_resource(super().list_resources())
        except Exception as exc:
            if not _is_expired_session_error(exc):
                return _with_user_info_resource({"resources": []})
            self._reset_remote_session()
            return _with_user_info_resource(super().list_resources())

    def read_resource(self, uri: str) -> Any:
        if uri == USER_INFO_RESOURCE_URI:
            return _read_user_info_result(self.user_info_markdown())
        try:
            return super().read_resource(uri)
        except Exception as exc:
            if not _is_expired_session_error(exc):
                raise
            self._reset_remote_session()
            return super().read_resource(uri)

    def user_info_markdown(self) -> str:
        lines = ["# Notion"]
        workspace = ""
        payload_getter = getattr(self._notion_auth, "get_oauth_payload", None)
        if callable(payload_getter):
            try:
                payload = payload_getter()
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                for key in ("workspace_name", "workspace", "workspace_id", "bot_id"):
                    value = payload.get(key)
                    if isinstance(value, dict):
                        workspace = _first_str(value, ("name", "display_name", "id"))
                    elif value is not None and str(value).strip():
                        workspace = str(value).strip()
                    if workspace:
                        break
        try:
            self.list_tools()
        except Exception:
            pass
        self_payload: Any = {}
        try:
            self_payload = _structured(self.call_tool("notion_get_self", {}))
        except Exception:
            self_payload = {}
        bot_name = ""
        bot_id = ""
        for item in _collect_dicts(self_payload):
            bot_name = bot_name or _first_str(item, ("name", "workspace_name"))
            bot_id = bot_id or _first_str(item, ("bot_id", "id"))
            if bot_name and bot_id:
                break
        if workspace:
            lines.append(f"Workspace: {workspace}")
        if bot_name or bot_id:
            integration = bot_name or "connected integration"
            if bot_id:
                integration = f"{integration} ({bot_id})"
            lines.append(f"Integration: {integration}")
        if len(lines) == 1:
            lines.append("Workspace: Notion OAuth connected")
        team_names: list[str] = []
        try:
            teams_payload = _structured(self.call_tool("notion_get_teams", {}))
            for item in _collect_dicts(teams_payload):
                name = _first_str(item, ("name", "title", "id"))
                if name and name not in team_names:
                    team_names.append(name)
        except Exception:
            team_names = []
        if team_names:
            shown = ", ".join(team_names[:5])
            extra = f" (+{len(team_names) - 5} more)" if len(team_names) > 5 else ""
            lines.append(f"Teamspaces: {shown}{extra}")
        lines.append("More: use notion_search / notion_fetch / notion_get_users / notion_get_teams.")
        return "\n".join(lines)
