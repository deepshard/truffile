"""Foreground app for a host-side Obsidian vault bridge."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

import httpx
from mcp.types import CallToolResult, TextContent

from truffile.app_runtime import ForegroundApp, ToolSpec, err, phosphor_icon_url

from bridge_client import ObsidianBridgeClient


def _text_result(text: str, *, structured: dict[str, Any] | None = None, is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text.strip() or "No response.")],
        structuredContent=structured or {},
        isError=is_error,
    )


def _local_result(payload: dict[str, Any]) -> CallToolResult:
    status = str(payload.get("status", "") or "")
    message = str(payload.get("message", "") or "")
    structured = {
        key: value
        for key, value in payload.items()
        if key not in {"status", "message", "tool"}
    }
    return _text_result(message or "Obsidian bridge returned an error.", structured=structured, is_error=status == "error")


def _format_files(directory: str, files: list[str]) -> CallToolResult:
    lines = [f"### Obsidian files in {directory}", f"{len(files)} entries."]
    lines.extend(f"- {path}" for path in files[:50])
    if len(files) > 50:
        lines.append(f"- ... {len(files) - 50} more")
    return _text_result("\n".join(lines), structured={"directory": directory, "files": files})


def _format_note(file_path: str, data: dict[str, Any]) -> CallToolResult:
    content = str(data.get("content", "") or "")
    lines = [f"### {file_path}", content or "(empty note)"]
    structured = {key: value for key, value in data.items() if key != "content"}
    structured["file_path"] = file_path
    return _text_result("\n\n".join(lines), structured=structured)


def _format_search(query: str, results: list[dict[str, Any]]) -> CallToolResult:
    lines = [f"### Obsidian search: {query}", f"{len(results)} results."]
    for index, item in enumerate(results[:20], start=1):
        path = str(item.get("path") or item.get("file_path") or item.get("file") or "Untitled")
        context = str(item.get("context") or item.get("snippet") or item.get("match") or "").strip()
        lines.append(f"- [{index}] {path}" + (f" - {context}" if context else ""))
    if len(results) > 20:
        lines.append(f"- ... {len(results) - 20} more")
    return _text_result("\n".join(lines), structured={"query": query, "results": results})


class ObsidianForegroundApp(ForegroundApp):
    def __init__(self) -> None:
        super().__init__("obsidian", logger_name="obsidian.foreground")
        self._client: ObsidianBridgeClient | None = None
        self._register_tools()

    def _get_client(self) -> ObsidianBridgeClient:
        if self._client is None:
            base_url = (os.getenv("OBSIDIAN_BRIDGE_BASE_URL") or "").strip()
            token = (os.getenv("OBSIDIAN_BRIDGE_TOKEN") or "").strip()
            if not base_url:
                raise ValueError("Missing OBSIDIAN_BRIDGE_BASE_URL")
            if not token:
                raise ValueError("Missing OBSIDIAN_BRIDGE_TOKEN")
            self._client = ObsidianBridgeClient(base_url=base_url, token=token)
        return self._client

    async def _bridge_error(self, exc: httpx.HTTPStatusError) -> CallToolResult:
        detail = ""
        try:
            detail = exc.response.text
        except Exception:
            detail = ""
        return _local_result(err(
            f"Bridge HTTP error: {exc.response.status_code}",
            response=detail[:1500],
        ))

    def _register_tools(self) -> None:
        @self.tool(
            ToolSpec(
                name="vault_status",
                description=(
                    "Call this tool first to verify the configured Obsidian vault bridge is reachable. "
                    "Use this tool directly instead of Bash when checking vault connectivity."
                ),
                icon=phosphor_icon_url("heartbeat"),
                annotations={"readOnlyHint": True, "destructiveHint": False},
            )
        )
        async def vault_status() -> CallToolResult:
            try:
                health = await self._get_client().health()
                vault = str(health.get("vault") or health.get("vault_path") or "").strip()
                suffix = f" for {vault}" if vault else ""
                return _text_result(f"Obsidian bridge reachable{suffix}.", structured=health)
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return _local_result(err(str(exc)))

        @self.tool(
            ToolSpec(
                name="list_vault_files",
                description=(
                    "List files and directories inside the configured Obsidian vault. "
                    "Use this tool directly instead of shell commands when inspecting vault contents."
                ),
                icon=phosphor_icon_url("folders"),
                annotations={"readOnlyHint": True, "destructiveHint": False},
            )
        )
        async def list_vault_files(directory: str = "/") -> CallToolResult:
            try:
                files = await self._get_client().list_files(directory)
                return _format_files(directory, files)
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return _local_result(err(str(exc)))

        @self.tool(
            ToolSpec(
                name="read_note",
                description=(
                    "Read a note from the configured Obsidian vault. "
                    "Use this tool directly instead of Bash or cat-like commands when note access is needed."
                ),
                icon=phosphor_icon_url("file-text"),
                annotations={"readOnlyHint": True, "destructiveHint": False},
            )
        )
        async def read_note(file_path: str) -> CallToolResult:
            try:
                data = await self._get_client().read_note(file_path)
                return _format_note(file_path, data)
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return _local_result(err(str(exc)))

        @self.tool(
            ToolSpec(
                name="write_note",
                description=(
                    "Create, overwrite, or append to a note in the configured Obsidian vault. "
                    "Use this as the canonical write path instead of shell redirection or Bash."
                ),
                icon=phosphor_icon_url("note-pencil"),
            )
        )
        async def write_note(file_path: str, content: str, append: bool = False) -> CallToolResult:
            try:
                result = await self._get_client().write_note(file_path, content, append=append)
                action = "Appended to" if append else "Wrote"
                structured = dict(result)
                structured["file_path"] = file_path
                structured["append"] = append
                return _text_result(f"{action} {file_path}.", structured=structured)
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return _local_result(err(str(exc)))

        @self.tool(
            ToolSpec(
                name="delete_note",
                description=(
                    "Delete a note from the configured Obsidian vault. "
                    "Use this tool directly instead of Bash when removing notes."
                ),
                icon=phosphor_icon_url("trash"),
            )
        )
        async def delete_note(file_path: str) -> CallToolResult:
            try:
                await self._get_client().delete_note(file_path)
                return _text_result(f"Deleted {file_path}.", structured={"file_path": file_path})
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return _local_result(err(str(exc)))

        @self.tool(
            ToolSpec(
                name="search_vault",
                description=(
                    "Full-text search across markdown notes in the configured Obsidian vault. "
                    "Use this tool directly instead of Bash grep-style commands when searching notes."
                ),
                icon=phosphor_icon_url("magnifying-glass"),
                annotations={"readOnlyHint": True, "destructiveHint": False},
            )
        )
        async def search_vault(query: str, context_length: int = 100) -> CallToolResult:
            try:
                results = await self._get_client().search(query, context_length=context_length)
                return _format_search(query, results)
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return _local_result(err(str(exc)))


app = ObsidianForegroundApp()


async def _verify() -> int:
    try:
        client = app._get_client()
        await client.health()
        await client.close()
    except Exception as exc:
        print(f"Obsidian bridge verification failed: {exc}", file=sys.stderr)
        return 1
    print("Obsidian bridge verification succeeded.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        raise SystemExit(asyncio.run(_verify()))
    app.run()
