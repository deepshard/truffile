#!/usr/bin/env python3
from __future__ import annotations

import inspect
import json
import os
from typing import Any

from mcp.types import CallToolResult, TextContent
from truffile.app_runtime import ForegroundApp, ToolSpec, phosphor_icon_url
from tools import TOOLS as _TOOL_SPECS, ToolDefinition


API_BASE = os.getenv("MENDER_API_BASE", "https://hosted.mender.io/api/management/v1").rstrip("/")
_TOKEN = os.getenv("MENDER_ACCESS_TOKEN", "").strip()


def _headers():
    return {
        "Authorization": f"Bearer {_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _make_tool_spec(entry: ToolDefinition) -> ToolSpec:
    supported = set(inspect.signature(ToolSpec).parameters)
    kwargs: dict[str, Any] = {
        "name": entry.name,
        "title": entry.title,
        "description": entry.description,
        "icon": phosphor_icon_url(entry.icon),
        "annotations": dict(entry.annotations),
    }
    if "structured_output" in supported:
        kwargs["structured_output"] = False
    if "readonly" in supported:
        kwargs["readonly"] = bool(entry.annotations.get("readOnlyHint"))
    return ToolSpec(**kwargs)


def _text_result(
    text: str, *, structured: dict[str, Any] | None = None, is_error: bool = False
) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text.strip())],
        structuredContent=structured,
        isError=is_error,
    )


async def _http_get(path: str) -> dict | list:
    import httpx

    url = f"{API_BASE}{path}"
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=_headers())
        resp.raise_for_status()
        return resp.json()


async def _http_post(path: str, data: dict) -> dict:
    import httpx

    url = f"{API_BASE}{path}"
    with httpx.Client(timeout=30) as client:
        resp = client.post(url, headers=_headers(), json=data)
        resp.raise_for_status()
        return resp.json()


async def _format_device_list(devices: list) -> CallToolResult:
    lines = [f"### Mender devices", f"{len(devices)} devices found."]
    refs: list[dict[str, Any]] = []
    for i, dev in enumerate(devices[:50], start=1):
        if not isinstance(dev, dict):
            continue
        did = dev.get("id", "")
        attrs = {a["name"]: a.get("value") for a in dev.get("attributes", []) if isinstance(a, dict)}
        status = dev.get("status", "unknown")
        name = attrs.get("name", "unnamed")
        host = attrs.get("hostname", attrs.get("mac", ""))
        artifact = attrs.get("artifact_name", "")
        lines.append(
            f"- [{i}] {name or did[:8]} | status={status} | id={did} | artifact={artifact}"
        )
        refs.append({"ref": i, "device_id": did, "name": name, "status": status})
    structured = {"devices": refs, "total": len(devices)}
    return _text_result("\n".join(lines), structured=structured)


async def _format_status_result(tool: str, *, message: str, is_error: bool = False) -> CallToolResult:
    return _text_result(f"Mender {tool}: {message}", is_error=is_error)


class MenderForegroundApp(ForegroundApp):
    def __init__(self) -> None:
        super().__init__("mender", logger_name="mender.foreground")
        self._register_tools()

    def _register_tools(self) -> None:
        specs = {e.name: _make_tool_spec(e) for e in _TOOL_SPECS}

        @self.tool(specs["list_devices"])
        async def list_devices_tool() -> CallToolResult:
            try:
                devices = await _http_get("/inventory/devices")
                return await _format_device_list(devices)
            except Exception as exc:
                return await _format_status_result("list_devices", message=str(exc), is_error=True)

        @self.tool(specs["get_device"])
        async def get_device_tool(device_id: str) -> CallToolResult:
            try:
                dev = await _http_get(f"/inventory/devices/{device_id}")
                return await _format_device_list([dev])
            except Exception as exc:
                return await _format_status_result("get_device", message=str(exc), is_error=True)

        @self.tool(specs["accept_device"])
        async def accept_device_tool(device_id: str) -> CallToolResult:
            try:
                await _http_post(
                    f"/inventory/devices/{device_id}/status", {"status": "accepted"}
                )
                return await _format_status_result("accept_device", message=f"Device {device_id} accepted")
            except Exception as exc:
                return await _format_status_result("accept_device", message=str(exc), is_error=True)

        @self.tool(specs["list_deployments"])
        async def list_deployments_tool() -> CallToolResult:
            try:
                deps = await _http_get("/deployments")
                lines = [f"### Mender deployments", f"{len(deps)} deployments found."]
                for i, dep in enumerate(deps[:50], start=1):
                    if not isinstance(dep, dict):
                        continue
                    did = dep.get("id", "")
                    state = dep.get("device_total", 0)
                    created = dep.get("created_ts", "")
                    lines.append(f"- [{i}] id={did[:8]}... devices={state} created={created}")
                return _text_result("\n".join(lines), structured={"deployments": deps[:50], "total": len(deps)})
            except Exception as exc:
                return await _format_status_result("list_deployments", message=str(exc), is_error=True)

        @self.tool(specs["get_deployment"])
        async def get_deployment_tool(deployment_id: str) -> CallToolResult:
            try:
                dep = await _http_get(f"/deployments/{deployment_id}")
                return _text_result(
                    json.dumps(dep, indent=2, default=str),
                    structured={"deployment": dep},
                )
            except Exception as exc:
                return await _format_status_result("get_deployment", message=str(exc), is_error=True)

        @self.tool(specs["list_releases"])
        async def list_releases_tool() -> CallToolResult:
            try:
                releases = await _http_get("/releases")
                lines = [f"### Mender releases", f"{len(releases)} releases found."]
                for i, rel in enumerate(releases[:50], start=1):
                    if not isinstance(rel, dict):
                        continue
                    name = rel.get("name", "unnamed")
                    mods = rel.get("artifact", {}).get("source", {}).get("meta", {})
                    lines.append(f"- [{i}] {name} | source={mods.get('source', 'unknown')}")
                return _text_result("\n".join(lines), structured={"releases": releases[:50], "total": len(releases)})
            except Exception as exc:
                return await _format_status_result("list_releases", message=str(exc), is_error=True)

        # Clean up metadata so the model doesn't try to parse output schemas
        for entry in _TOOL_SPECS:
            tool = self._mcp._tool_manager.get_tool(entry.name)
            metadata = getattr(tool, "fn_metadata", None)
            if metadata is not None:
                metadata.output_schema = None
                metadata.output_model = None
                metadata.wrap_output = False


app = MenderForegroundApp()

if __name__ == "__main__":
    app.run()