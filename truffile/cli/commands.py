from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    name: str
    description: str
    has_arg: bool = False
    arg_hint: str = ""


CHAT_COMMANDS: list[SlashCommand] = [
    SlashCommand("/help", "show available commands"),
    SlashCommand("/threads", "list and switch Convo threads"),
    SlashCommand("/tasks", "thread picker (one-release alias)"),
    SlashCommand("/rename", "rename current thread", has_arg=True, arg_hint="<name>"),
    SlashCommand("/title", "show current thread title"),
    SlashCommand("/history", "show current thread history"),
    SlashCommand("/main", "switch explicitly to Main"),
    SlashCommand("/new", "start a new side thread"),
    SlashCommand("/interrupt", "interrupt work in current thread"),
    SlashCommand("/hide", "hide a thread on this machine", has_arg=True, arg_hint="[name|id]"),
    SlashCommand("/restore", "restore a locally hidden thread", has_arg=True, arg_hint="[name|id]"),
    SlashCommand("/apps", "list installed apps"),
    SlashCommand("/deploy", "deploy an app to device", has_arg=True, arg_hint="<path>"),
    SlashCommand("/delete", "delete app or locally hide task alias", has_arg=True, arg_hint="app|task"),
    SlashCommand("/create", "scaffold a new app", has_arg=True, arg_hint="<name>"),
    SlashCommand("/devices", "list connected devices"),
    SlashCommand("/exit", "exit Convo"),
]


INFER_COMMANDS: list[SlashCommand] = [
    SlashCommand("/help", "show available commands"),
    SlashCommand("/history", "show conversation history"),
    SlashCommand("/reset", "clear conversation history"),
    SlashCommand("/models", "switch inference model"),
    SlashCommand("/config", "show current config"),
    SlashCommand("/reasoning", "toggle reasoning", has_arg=True, arg_hint="on|off"),
    SlashCommand("/stream", "toggle streaming", has_arg=True, arg_hint="on|off"),
    SlashCommand("/json", "toggle JSON mode", has_arg=True, arg_hint="on|off"),
    SlashCommand("/tools", "toggle tool use", has_arg=True, arg_hint="on|off"),
    SlashCommand("/max_tokens", "set max response tokens", has_arg=True, arg_hint="<int>"),
    SlashCommand("/temperature", "set temperature", has_arg=True, arg_hint="<float|off>"),
    SlashCommand("/top_p", "set top_p", has_arg=True, arg_hint="<float|off>"),
    SlashCommand("/max_rounds", "set max tool rounds", has_arg=True, arg_hint="<int>"),
    SlashCommand("/system", "set system prompt", has_arg=True, arg_hint="<text|off>"),
    SlashCommand("/mcp", "manage MCP connections", has_arg=True, arg_hint="connect|disconnect|status|tools"),
    SlashCommand("/attach", "attach an image", has_arg=True, arg_hint="<path-or-url>"),
    SlashCommand("/create", "scaffold a new app", has_arg=True, arg_hint="<name>"),
    SlashCommand("/exit", "exit"),
]
