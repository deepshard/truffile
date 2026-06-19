"""HTTP client for the host-side Obsidian vault bridge."""

from __future__ import annotations

from typing import Any

import httpx


class ObsidianBridgeClient:
    def __init__(self, base_url: str, token: str, timeout: float = 20.0) -> None:
        normalized = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=normalized,
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )

    async def health(self) -> dict[str, Any]:
        resp = await self._http.get("/health")
        resp.raise_for_status()
        return resp.json()

    async def list_files(self, directory: str = "/") -> list[str]:
        resp = await self._http.get("/files", params={"directory": directory})
        resp.raise_for_status()
        return resp.json().get("files", [])

    async def read_note(self, file_path: str) -> dict[str, Any]:
        resp = await self._http.get("/note", params={"path": file_path})
        resp.raise_for_status()
        return resp.json()

    async def write_note(self, file_path: str, content: str, *, append: bool = False) -> dict[str, Any]:
        method = self._http.post if append else self._http.put
        resp = await method(
            "/note",
            params={"path": file_path},
            content=content,
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_note(self, file_path: str) -> dict[str, Any]:
        resp = await self._http.delete("/note", params={"path": file_path})
        resp.raise_for_status()
        return resp.json()

    async def search(self, query: str, context_length: int = 100) -> list[dict[str, Any]]:
        resp = await self._http.post(
            "/search",
            json={"query": query, "context_length": context_length},
        )
        resp.raise_for_status()
        return resp.json().get("results", [])

    async def close(self) -> None:
        await self._http.aclose()
