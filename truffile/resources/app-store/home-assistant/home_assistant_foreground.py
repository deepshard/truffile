from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from mcp.types import CallToolResult, TextContent

from truffile.app_runtime import ForegroundApp, ToolSpec, err, phosphor_icon_url, text_from_mcp_result

from ha_mcp_client import HomeAssistantMcpClient
from safety import check_climate_temperature, check_cover_position, check_turn_on_off


CONTEXT_RESOURCE_URI = "homeassistant://assist/context-snapshot"


def _args(**values: Any) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _safe_name(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _text_result(text: str, *, structured: dict[str, Any] | None = None, is_error: bool = False) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text.strip() or "No response.")],
        structuredContent=structured or {},
        isError=is_error,
    )


def _local_result(payload: dict[str, Any]) -> CallToolResult:
    status = str(payload.get("status", "") or "")
    message = str(payload.get("message", "") or "")
    is_error = status == "error"
    structured = {
        key: value
        for key, value in payload.items()
        if key not in {"status", "message", "tool"}
    }
    return _text_result(message or ("Home Assistant returned an error." if is_error else "Home Assistant completed."), structured=structured, is_error=is_error)


def _remote_result(name: str, payload: Any) -> CallToolResult:
    if isinstance(payload, CallToolResult):
        return payload
    if isinstance(payload, dict) and ("content" in payload or "structuredContent" in payload or "isError" in payload):
        text = text_from_mcp_result(payload) or f"Home Assistant MCP tool {name} completed."
        structured = payload.get("structuredContent") if isinstance(payload.get("structuredContent"), dict) else {}
        return _text_result(text, structured=structured, is_error=bool(payload.get("isError")))
    if isinstance(payload, dict):
        return _local_result(payload)
    return _text_result(str(payload or f"Home Assistant MCP tool {name} completed."))


class HomeAssistantForegroundApp(ForegroundApp):
    def __init__(self, *, client: HomeAssistantMcpClient | None = None) -> None:
        super().__init__("home-assistant", logger_name="home_assistant.foreground")
        self._client = client
        self._register_tools()

    def _get_client(self) -> HomeAssistantMcpClient:
        if self._client is None:
            self._client = HomeAssistantMcpClient()
        return self._client

    async def _call_remote_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        try:
            return _remote_result(name, await self._get_client().call_tool(name, arguments))
        except Exception as exc:
            return _local_result(err(str(exc), tool=name))

    def _register_tools(self) -> None:
        @self.tool(
            ToolSpec(
                name="ha_check_connection",
                description="Check whether the configured Home Assistant base URL, token, and /api/mcp endpoint work.",
                icon=phosphor_icon_url("PlugsConnected"),
                annotations={"readOnlyHint": True, "destructiveHint": False},
            )
        )
        async def ha_check_connection_tool() -> CallToolResult:
            result = await self._get_client().verify_payload()
            if result["ok"]:
                return _text_result(
                    str(result["message"]),
                    structured={"base_url": result["base_url"], "mcp_url": result["mcp_url"]},
                )
            return _text_result(
                str(result["message"]),
                structured={"base_url": result["base_url"], "mcp_url": result["mcp_url"]},
                is_error=True,
            )

        @self.tool(
            ToolSpec(
                name="ha_list_capabilities",
                description="List Home Assistant MCP tools, resources, and prompts currently exposed by the user's Assist configuration.",
                icon=phosphor_icon_url("ListChecks"),
                annotations={"readOnlyHint": True, "destructiveHint": False},
            )
        )
        async def ha_list_capabilities_tool() -> CallToolResult:
            client = self._get_client()
            try:
                tools = await client.list_tools()
                resources = await client.list_resources()
                prompts = await client.list_prompts()
            except Exception as exc:
                return _local_result(err(str(exc), tool="ha_list_capabilities"))
            tool_names = [str(item.get("name", "")) for item in tools if isinstance(item, dict) and item.get("name")]
            resource_uris = [str(item.get("uri", "")) for item in resources if isinstance(item, dict) and item.get("uri")]
            prompt_names = [str(item.get("name", "")) for item in prompts if isinstance(item, dict) and item.get("name")]
            lines = [
                "### Home Assistant capabilities",
                f"{len(tools)} tools, {len(resources)} resources, {len(prompts)} prompts exposed.",
            ]
            if tool_names:
                lines.append("Tools: " + ", ".join(tool_names[:20]) + (" ..." if len(tool_names) > 20 else ""))
            if resource_uris:
                lines.append("Resources: " + ", ".join(resource_uris[:10]) + (" ..." if len(resource_uris) > 10 else ""))
            if prompt_names:
                lines.append("Prompts: " + ", ".join(prompt_names[:10]) + (" ..." if len(prompt_names) > 10 else ""))
            return _text_result(
                "\n".join(lines),
                structured={"tools": tools, "resources": resources, "prompts": prompts},
            )

        @self.tool(
            ToolSpec(
                name="ha_get_live_context",
                description=(
                    "Read current Home Assistant live context for matching entities. Use before controlling devices. "
                    "Filter by name, area, or domain when possible."
                ),
                icon=phosphor_icon_url("HouseLine"),
                annotations={"readOnlyHint": True, "destructiveHint": False},
            )
        )
        async def ha_get_live_context_tool(
            entity_name: str | None = None,
            area: str | None = None,
            domain: str | None = None,
        ) -> CallToolResult:
            return await self._call_remote_tool(
                "GetLiveContext",
                _args(name=_safe_name(entity_name), area=_safe_name(area), domain=_safe_name(domain)),
            )

        @self.tool(
            ToolSpec(
                name="ha_get_context_snapshot",
                description="Read the Home Assistant assist context snapshot resource for a compact view of exposed devices and state.",
                icon=phosphor_icon_url("FileText"),
                annotations={"readOnlyHint": True, "destructiveHint": False},
            )
        )
        async def ha_get_context_snapshot_tool() -> CallToolResult:
            try:
                return _remote_result("ha_get_context_snapshot", await self._get_client().read_resource(CONTEXT_RESOURCE_URI))
            except Exception as exc:
                return _local_result(err(str(exc), resource=CONTEXT_RESOURCE_URI))

        @self.tool(
            ToolSpec(
                name="ha_turn_on",
                description=(
                    "Turn on a Home Assistant entity or area by name/domain. Read live context first. "
                    "Locks, alarms, garage/gate covers, scripts, broad security actions, and unconfirmed scenes are blocked."
                ),
                icon=phosphor_icon_url("Power"),
            )
        )
        async def ha_turn_on_tool(
            entity_name: str | None = None,
            area: str | None = None,
            domain: str | None = None,
            confirm: bool = False,
            confirmation_text: str = "",
        ) -> CallToolResult:
            decision = check_turn_on_off(
                action="turn_on",
                name=entity_name,
                area=area,
                domain=domain,
                confirm=confirm,
                confirmation_text=confirmation_text,
            )
            if not decision.allowed:
                return _local_result(err(
                    decision.message,
                    requires_confirmation=decision.requires_confirmation,
                    tool="ha_turn_on",
                ))
            return await self._call_remote_tool(
                "HassTurnOn",
                _args(name=_safe_name(entity_name), area=_safe_name(area), domain=_safe_name(domain)),
            )

        @self.tool(
            ToolSpec(
                name="ha_turn_off",
                description=(
                    "Turn off a Home Assistant entity or area by name/domain. Read live context first. "
                    "Safety-sensitive security, lock, cover, and broad whole-home actions require explicit confirmation or are blocked."
                ),
                icon=phosphor_icon_url("Power"),
            )
        )
        async def ha_turn_off_tool(
            entity_name: str | None = None,
            area: str | None = None,
            domain: str | None = None,
            confirm: bool = False,
            confirmation_text: str = "",
        ) -> CallToolResult:
            decision = check_turn_on_off(
                action="turn_off",
                name=entity_name,
                area=area,
                domain=domain,
                confirm=confirm,
                confirmation_text=confirmation_text,
            )
            if not decision.allowed:
                return _local_result(err(
                    decision.message,
                    requires_confirmation=decision.requires_confirmation,
                    tool="ha_turn_off",
                ))
            return await self._call_remote_tool(
                "HassTurnOff",
                _args(name=_safe_name(entity_name), area=_safe_name(area), domain=_safe_name(domain)),
            )

        @self.tool(
            ToolSpec(
                name="ha_set_light",
                description="Set light brightness or color in Home Assistant. Use name or area and read live context first.",
                icon=phosphor_icon_url("Lightbulb"),
            )
        )
        async def ha_set_light_tool(
            entity_name: str | None = None,
            area: str | None = None,
            brightness: int | None = None,
            color: str | None = None,
            color_temp: int | None = None,
        ) -> CallToolResult:
            if brightness is not None and (brightness < 0 or brightness > 100):
                return _local_result(err("Brightness must be between 0 and 100.", tool="ha_set_light"))
            return await self._call_remote_tool(
                "HassLightSet",
                _args(
                    name=_safe_name(entity_name),
                    area=_safe_name(area),
                    brightness=brightness,
                    color=_safe_name(color),
                    color_temp=color_temp,
                ),
            )

        @self.tool(
            ToolSpec(
                name="ha_set_climate_temperature",
                description=(
                    "Set a Home Assistant climate device temperature. The app blocks setpoints outside 50-85 F or 10-30 C."
                ),
                icon=phosphor_icon_url("Thermometer"),
            )
        )
        async def ha_set_climate_temperature_tool(entity_name: str, temperature: float) -> CallToolResult:
            decision = check_climate_temperature(temperature)
            if not decision.allowed:
                return _local_result(err(decision.message, tool="ha_set_climate_temperature"))
            return await self._call_remote_tool(
                "HassClimateSetTemperature",
                _args(name=_safe_name(entity_name), temperature=temperature),
            )

        @self.tool(
            ToolSpec(
                name="ha_set_cover_position",
                description=(
                    "Set a non-garage, non-gate Home Assistant cover position from 0 to 100. "
                    "Requires explicit confirmation because it moves physical equipment."
                ),
                icon=phosphor_icon_url("Garage"),
            )
        )
        async def ha_set_cover_position_tool(
            entity_name: str,
            position: int,
            confirm: bool = False,
            confirmation_text: str = "",
        ) -> CallToolResult:
            decision = check_cover_position(
                name=entity_name,
                position=position,
                confirm=confirm,
                confirmation_text=confirmation_text,
            )
            if not decision.allowed:
                return _local_result(err(
                    decision.message,
                    requires_confirmation=decision.requires_confirmation,
                    tool="ha_set_cover_position",
                ))
            return await self._call_remote_tool("HassSetPosition", _args(name=_safe_name(entity_name), position=position))

        @self.tool(
            ToolSpec(
                name="ha_calendar_get_events",
                description="Read events from an exposed Home Assistant calendar between optional ISO dates.",
                icon=phosphor_icon_url("CalendarBlank"),
                annotations={"readOnlyHint": True, "destructiveHint": False},
            )
        )
        async def ha_calendar_get_events_tool(
            calendar_name: str | None = None,
            start_date: str | None = None,
            end_date: str | None = None,
        ) -> CallToolResult:
            return await self._call_remote_tool(
                "calendar_get_events",
                _args(name=_safe_name(calendar_name), start_date=_safe_name(start_date), end_date=_safe_name(end_date)),
            )

        @self.tool(
            ToolSpec(
                name="ha_todo_get_items",
                description="Read items from an exposed Home Assistant todo list.",
                icon=phosphor_icon_url("ClipboardText"),
                annotations={"readOnlyHint": True, "destructiveHint": False},
            )
        )
        async def ha_todo_get_items_tool(todo_list_name: str | None = None) -> CallToolResult:
            return await self._call_remote_tool("todo_get_items", _args(name=_safe_name(todo_list_name)))

        @self.tool(
            ToolSpec(
                name="ha_todo_add_item",
                description="Add an item to an exposed Home Assistant todo list.",
                icon=phosphor_icon_url("PlusCircle"),
            )
        )
        async def ha_todo_add_item_tool(item: str, todo_list_name: str | None = None) -> CallToolResult:
            return await self._call_remote_tool("HassListAddItem", _args(item=item, name=_safe_name(todo_list_name)))

        @self.tool(
            ToolSpec(
                name="ha_todo_complete_item",
                description="Mark an item complete in an exposed Home Assistant todo list.",
                icon=phosphor_icon_url("CheckCircle"),
            )
        )
        async def ha_todo_complete_item_tool(item: str, todo_list_name: str | None = None) -> CallToolResult:
            return await self._call_remote_tool("HassListCompleteItem", _args(item=item, name=_safe_name(todo_list_name)))


async def _verify_async() -> int:
    try:
        client = HomeAssistantMcpClient()
        success, message = await client.verify()
    except Exception as exc:
        print(f"Home Assistant verification failed: {exc}", flush=True)
        return 1

    print(message, flush=True)
    return 0 if success else 1


def verify() -> int:
    return asyncio.run(_verify_async())


app = HomeAssistantForegroundApp()


def main() -> int:
    parser = argparse.ArgumentParser(description="Home Assistant foreground app")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify HOME_ASSISTANT_BASE_URL, HOME_ASSISTANT_TOKEN, and the /api/mcp endpoint.",
    )
    args = parser.parse_args()
    if args.verify:
        return verify()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
