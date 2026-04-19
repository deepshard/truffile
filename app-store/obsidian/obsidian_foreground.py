"""Foreground app for a host-side Obsidian vault bridge."""

from __future__ import annotations

from typing import Any
import os

import httpx

from truffile.app_runtime import ForegroundApp, ToolSpec, err, ok, phosphor_icon_url

from bridge_client import ObsidianBridgeClient


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

    async def _bridge_error(self, exc: httpx.HTTPStatusError) -> dict[str, Any]:
        detail = ""
        try:
            detail = exc.response.text
        except Exception:
            detail = ""
        return err(
            f"Bridge HTTP error: {exc.response.status_code}",
            response=detail[:1500],
        )

    def _register_tools(self) -> None:
        @self.tool(
            ToolSpec(
                name="vault_status",
                description=(
                    "Call this tool first to verify the configured Obsidian vault bridge is reachable. "
                    "Use this tool directly instead of Bash when checking vault connectivity."
                ),
                icon=phosphor_icon_url("heartbeat"),
                readonly=True,
            )
        )
        async def vault_status() -> dict[str, Any]:
            try:
                return ok("Obsidian bridge reachable", **(await self._get_client().health()))
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return err(str(exc))

        @self.tool(
            ToolSpec(
                name="list_vault_files",
                description=(
                    "List files and directories inside the configured Obsidian vault. "
                    "Use this tool directly instead of shell commands when inspecting vault contents."
                ),
                icon=phosphor_icon_url("folders"),
                readonly=True,
            )
        )
        async def list_vault_files(directory: str = "/") -> dict[str, Any]:
            try:
                files = await self._get_client().list_files(directory)
                return ok(f"{len(files)} entries in {directory}", directory=directory, files=files)
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return err(str(exc))

        @self.tool(
            ToolSpec(
                name="read_note",
                description=(
                    "Read a note from the configured Obsidian vault. "
                    "Use this tool directly instead of Bash or cat-like commands when note access is needed."
                ),
                icon=phosphor_icon_url("file-text"),
                readonly=True,
            )
        )
        async def read_note(file_path: str) -> dict[str, Any]:
            try:
                data = await self._get_client().read_note(file_path)
                return ok(f"Read {file_path}", file_path=file_path, **data)
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return err(str(exc))

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
        async def write_note(file_path: str, content: str, append: bool = False) -> dict[str, Any]:
            try:
                result = await self._get_client().write_note(file_path, content, append=append)
                action = "Appended to" if append else "Wrote"
                return ok(f"{action} {file_path}", file_path=file_path, **result)
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return err(str(exc))

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
        async def delete_note(file_path: str) -> dict[str, Any]:
            try:
                await self._get_client().delete_note(file_path)
                return ok(f"Deleted {file_path}", file_path=file_path)
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return err(str(exc))

        @self.tool(
            ToolSpec(
                name="search_vault",
                description=(
                    "Full-text search across markdown notes in the configured Obsidian vault. "
                    "Use this tool directly instead of Bash grep-style commands when searching notes."
                ),
                icon=phosphor_icon_url("magnifying-glass"),
                readonly=True,
            )
        )
        async def search_vault(query: str, context_length: int = 100) -> dict[str, Any]:
            try:
                results = await self._get_client().search(query, context_length=context_length)
                return ok(f"{len(results)} results for '{query}'", query=query, results=results)
            except httpx.HTTPStatusError as exc:
                return await self._bridge_error(exc)
            except Exception as exc:
                return err(str(exc))


app = ObsidianForegroundApp()


if __name__ == "__main__":
    app.run()
