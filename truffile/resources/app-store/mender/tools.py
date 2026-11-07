"""Canonical foreground tool metadata for Mender IoT."""

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
    ToolDefinition(
        name="list_devices",
        title="List Devices",
        description="List all Mender devices connected to your tenant. Returns device IDs, attributes, status, and last check-in time.",
        icon="device-desktop",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="get_device",
        title="Get Device",
        description="Get full details for a specific Mender device by ID, including inventory attributes and status.",
        icon="device-desktop",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="accept_device",
        title="Accept Device",
        description="Accept a pending Mender device so it can receive deployments.",
        icon="circle-wrench",
        annotations={"readOnlyHint": False, "destructiveHint": False},
    ),
    ToolDefinition(
        name="list_deployments",
        title="List Deployments",
        description="List recent Mender deployments with status, device count, and created time.",
        icon="cloud-arrow-up",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="get_deployment",
        title="Get Deployment",
        description="Get details for a specific deployment by ID, including devices and artifacts.",
        icon="file-text",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
    ToolDefinition(
        name="list_releases",
        title="List Releases",
        description="List all software releases/artifacts in Mender.",
        icon="package",
        annotations={"readOnlyHint": True, "destructiveHint": False},
    ),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}