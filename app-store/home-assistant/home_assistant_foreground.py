from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from truffile.app_runtime import ForegroundApp, ToolSpec, err, ok, phosphor_icon_url

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


class HomeAssistantForegroundApp(ForegroundApp):
    def __init__(self, *, client: HomeAssistantMcpClient | None = None) -> None:
        super().__init__("home-assistant", logger_name="home_assistant.foreground")
        self._client = client
        self._register_tools()

    def _get_client(self) -> HomeAssistantMcpClient:
        if self._client is None:
            self._client = HomeAssistantMcpClient()
        return self._client

    async def _call_remote_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self._get_client().call_tool(name, arguments)
        except Exception as exc:
            return err(str(exc), tool=name)

    def _register_tools(self) -> None:
        @self.tool(
            ToolSpec(
                name="ha_check_connection",
                description="Check whether the configured Home Assistant base URL, token, and /api/mcp endpoint work.",
                icon=phosphor_icon_url("PlugsConnected"),
                readonly=True,
            )
        )
        async def ha_check_connection_tool() -> dict[str, Any]:
            result = await self._get_client().verify_payload()
            if result["ok"]:
                return ok(result["message"], base_url=result["base_url"], mcp_url=result["mcp_url"])
            return err(result["message"], base_url=result["base_url"], mcp_url=result["mcp_url"])

        @self.tool(
            ToolSpec(
                name="ha_list_capabilities",
                description="List Home Assistant MCP tools, resources, and prompts currently exposed by the user's Assist configuration.",
                icon=phosphor_icon_url("ListChecks"),
                readonly=True,
            )
        )
        async def ha_list_capabilities_tool() -> dict[str, Any]:
            client = self._get_client()
            try:
                tools = await client.list_tools()
                resources = await client.list_resources()
                prompts = await client.list_prompts()
            except Exception as exc:
                return err(str(exc), tool="ha_list_capabilities")
            return ok(
                "Loaded Home Assistant MCP capabilities.",
                tools=tools,
                resources=resources,
                prompts=prompts,
            )

        @self.tool(
            ToolSpec(
                name="ha_get_live_context",
                description=(
                    "Read current Home Assistant live context for matching entities. Use before controlling devices. "
                    "Filter by name, area, or domain when possible."
                ),
                icon=phosphor_icon_url("HouseLine"),
                readonly=True,
            )
        )
        async def ha_get_live_context_tool(
            entity_name: str | None = None,
            area: str | None = None,
            domain: str | None = None,
        ) -> dict[str, Any]:
            return await self._call_remote_tool(
                "GetLiveContext",
                _args(name=_safe_name(entity_name), area=_safe_name(area), domain=_safe_name(domain)),
            )

        @self.tool(
            ToolSpec(
                name="ha_get_context_snapshot",
                description="Read the Home Assistant assist context snapshot resource for a compact view of exposed devices and state.",
                icon=phosphor_icon_url("FileText"),
                readonly=True,
            )
        )
        async def ha_get_context_snapshot_tool() -> dict[str, Any]:
            try:
                return await self._get_client().read_resource(CONTEXT_RESOURCE_URI)
            except Exception as exc:
                return err(str(exc), resource=CONTEXT_RESOURCE_URI)

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
        ) -> dict[str, Any]:
            decision = check_turn_on_off(
                action="turn_on",
                name=entity_name,
                area=area,
                domain=domain,
                confirm=confirm,
                confirmation_text=confirmation_text,
            )
            if not decision.allowed:
                return err(
                    decision.message,
                    requires_confirmation=decision.requires_confirmation,
                    tool="ha_turn_on",
                )
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
        ) -> dict[str, Any]:
            decision = check_turn_on_off(
                action="turn_off",
                name=entity_name,
                area=area,
                domain=domain,
                confirm=confirm,
                confirmation_text=confirmation_text,
            )
            if not decision.allowed:
                return err(
                    decision.message,
                    requires_confirmation=decision.requires_confirmation,
                    tool="ha_turn_off",
                )
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
        ) -> dict[str, Any]:
            if brightness is not None and (brightness < 0 or brightness > 100):
                return err("Brightness must be between 0 and 100.", tool="ha_set_light")
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
        async def ha_set_climate_temperature_tool(entity_name: str, temperature: float) -> dict[str, Any]:
            decision = check_climate_temperature(temperature)
            if not decision.allowed:
                return err(decision.message, tool="ha_set_climate_temperature")
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
        ) -> dict[str, Any]:
            decision = check_cover_position(
                name=entity_name,
                position=position,
                confirm=confirm,
                confirmation_text=confirmation_text,
            )
            if not decision.allowed:
                return err(
                    decision.message,
                    requires_confirmation=decision.requires_confirmation,
                    tool="ha_set_cover_position",
                )
            return await self._call_remote_tool("HassSetPosition", _args(name=_safe_name(entity_name), position=position))

        @self.tool(
            ToolSpec(
                name="ha_calendar_get_events",
                description="Read events from an exposed Home Assistant calendar between optional ISO dates.",
                icon=phosphor_icon_url("CalendarBlank"),
                readonly=True,
            )
        )
        async def ha_calendar_get_events_tool(
            calendar_name: str | None = None,
            start_date: str | None = None,
            end_date: str | None = None,
        ) -> dict[str, Any]:
            return await self._call_remote_tool(
                "calendar_get_events",
                _args(name=_safe_name(calendar_name), start_date=_safe_name(start_date), end_date=_safe_name(end_date)),
            )

        @self.tool(
            ToolSpec(
                name="ha_todo_get_items",
                description="Read items from an exposed Home Assistant todo list.",
                icon=phosphor_icon_url("ClipboardText"),
                readonly=True,
            )
        )
        async def ha_todo_get_items_tool(todo_list_name: str | None = None) -> dict[str, Any]:
            return await self._call_remote_tool("todo_get_items", _args(name=_safe_name(todo_list_name)))

        @self.tool(
            ToolSpec(
                name="ha_todo_add_item",
                description="Add an item to an exposed Home Assistant todo list.",
                icon=phosphor_icon_url("PlusCircle"),
            )
        )
        async def ha_todo_add_item_tool(item: str, todo_list_name: str | None = None) -> dict[str, Any]:
            return await self._call_remote_tool("HassListAddItem", _args(item=item, name=_safe_name(todo_list_name)))

        @self.tool(
            ToolSpec(
                name="ha_todo_complete_item",
                description="Mark an item complete in an exposed Home Assistant todo list.",
                icon=phosphor_icon_url("CheckCircle"),
            )
        )
        async def ha_todo_complete_item_tool(item: str, todo_list_name: str | None = None) -> dict[str, Any]:
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
