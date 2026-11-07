"""Static Turkish Airlines MCP tool metadata for default-app publishing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    title: str
    description: str
    icon: str
    annotations: dict[str, bool]


TOOLS = [
    ToolDefinition(name="search_flights", title="Search Flights", description="Search for available Turkish Airlines flights by origin, destination, date, and passengers.", icon="airplane", annotations={"readOnlyHint": True, "destructiveHint": False}),
    ToolDefinition(name="flight_status", title="Flight Status", description="Get real-time status of a Turkish Airlines flight by flight number.", icon="airplane-clock", annotations={"readOnlyHint": True, "destructiveHint": False}),
    ToolDefinition(name="booking_details", title="Booking Details", description="Retrieve booking details using PNR and surname.", icon="clipboard", annotations={"readOnlyHint": True, "destructiveHint": False}),
    ToolDefinition(name="check_in", title="Check In", description="Check in for a Turkish Airlines flight using PNR and surname.", icon="door-open", annotations={"readOnlyHint": False, "destructiveHint": False}),
    ToolDefinition(name="miles_profile", title="Miles&Smiles Profile", description="Get Miles&Smiles account information and member details.", icon="badge", annotations={"readOnlyHint": True, "destructiveHint": False}),
    ToolDefinition(name="miles_balance", title="Miles Balance", description="Check current Miles&Smiles balance and status.", icon="coins", annotations={"readOnlyHint": True, "destructiveHint": False}),
    ToolDefinition(name="miles_history", title="Miles History", description="Get Miles&Smiles transaction history and point movements.", icon="list", annotations={"readOnlyHint": True, "destructiveHint": False}),
    ToolDefinition(name="cancel_booking", title="Cancel Booking", description="Cancel or modify a Turkish Airlines booking.", icon="x-circle", annotations={"readOnlyHint": False, "destructiveHint": True}),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}