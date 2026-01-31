from __future__ import annotations

from typing import List, Tuple
import json
import re

from truffle.infer.gencfg_pb2 import ResponseFormat

from .common import THINK_TAGS
from .tooling import Tool


TOOL_TAGS = ["<toolcall>", "</toolcall>"]
tool_tag_pattern = re.compile(f"{TOOL_TAGS[0]}(.*?){TOOL_TAGS[1]}", re.DOTALL)


class AgentPromptBuilder:
    def extract_tool_calls(self, response: str) -> Tuple[List[dict], str]:
        tool_calls: List[dict] = []
        matches = tool_tag_pattern.findall(response)
        if not matches:
            return tool_calls, response
        for match in matches:
            try:
                tool_call = json.loads(match.strip())
                tool_calls.append(tool_call)
            except json.JSONDecodeError:
                continue
        clean_response = tool_tag_pattern.sub("", response).strip()
        return tool_calls, clean_response


def _build_tool_call_response_format_non_reasoning(
    req, available_tools: List[Tool], allow_parallel: bool = False
) -> None:
    def get_tag_for_tool(tool: Tool) -> dict:
        begin = f"{TOOL_TAGS[0]}\n" + '{"tool": ' + f'"{tool.name}", "args": '
        end = "}" + f"{TOOL_TAGS[1]}\n"
        return {
            "begin": begin,
            "content": {"type": "json_schema", "json_schema": tool.input_schema},
            "end": end,
        }

    structural_tag = {
        "type": "structural_tag",
        "format": {
            "type": "triggered_tags",
            "triggers": [TOOL_TAGS[0]],
            "tags": [get_tag_for_tool(tool) for tool in available_tools],
            "stop_after_first": not allow_parallel,
        },
    }
    req.cfg.response_format.format = ResponseFormat.STRUCTURAL_TAG
    req.cfg.response_format.schema = json.dumps(structural_tag, indent=0)


def _build_tool_call_response_format(
    req, available_tools: List[Tool], allow_parallel: bool = False
) -> None:
    def get_tag_for_tool(tool: Tool) -> dict:
        begin = f"{TOOL_TAGS[0]}\n" + '{"tool": ' + f'"{tool.name}", "args": '
        end = "}" + f"{TOOL_TAGS[1]}\n"
        return {
            "begin": begin,
            "content": {"type": "json_schema", "json_schema": tool.input_schema},
            "end": end,
        }

    structural_tag = {
        "type": "structural_tag",
        "format": {
            "type": "sequence",
            "elements": [
                {
                    "type": "tag",
                    "begin": "",
                    "content": {"type": "any_text"},
                    "end": THINK_TAGS[1],
                },
                {
                    "type": "triggered_tags",
                    "triggers": [TOOL_TAGS[0]],
                    "tags": [get_tag_for_tool(tool) for tool in available_tools],
                    "stop_after_first": not allow_parallel,
                },
            ],
        },
    }
    req.cfg.response_format.format = ResponseFormat.STRUCTURAL_TAG
    req.cfg.response_format.schema = json.dumps(structural_tag, indent=0)
