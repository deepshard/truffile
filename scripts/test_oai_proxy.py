#!/usr/bin/env python3
"""Smoke test for the local OpenAI-compatible proxy."""

from __future__ import annotations

import argparse
import os
from typing import Any, Dict, List
try:
    from openai import OpenAI
except ImportError:
    raise ImportError("Please install the 'openai' package to run this test script.")

def _print_header(title: str) -> None:
    print("\n" + "=" * 8 + f" {title} " + "=" * 8)


def test_basic(client: OpenAI, model: str) -> None:
    _print_header("basic")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Say hello in one sentence."}],
        max_tokens=2048,
        temperature=0.7,
        top_p=0.9,
    )
    msg = resp.choices[0].message
    print("content:", msg.content)


def test_json_schema(client: OpenAI, model: str) -> None:
    _print_header("json_schema")
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["answer", "confidence"],
    }
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "What is 2+2? Respond as JSON."}],
        response_format={"type": "json_schema", "json_schema": schema},
        max_tokens=2048,
    )
    msg = resp.choices[0].message
    print("content:", msg.content)


def test_tools(client: OpenAI, model: str) -> None:
    _print_header("tools")
    tools: List[Dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "get_time",
                "description": "Return the current time in ISO-8601",
                "parameters": {
                    "type": "object",
                    "properties": {"tz": {"type": "string"}},
                    "required": [],
                },
            },
        }
    ]
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "What time is it? Use the tool."}],
        tools=tools,
        tool_choice="auto",
        max_tokens=2048,
    )
    msg = resp.choices[0].message
    print("tool_calls:", msg.tool_calls)
    print("content:", msg.content)


def test_stream(client: OpenAI, model: str) -> None:
    _print_header("stream")
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Stream a short haiku."}],
        max_tokens=2048,
        stream=True,
    )
    parts: List[str] = []
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta and delta.content:
            parts.append(delta.content)
    print("content:", "".join(parts))


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for OpenAI proxy")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1", help="Proxy base URL")
    parser.add_argument("--model", default="auto", help="Model name or UUID")
    parser.add_argument("--no-stream", action="store_true", help="Skip streaming test")
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "test")
    client = OpenAI(base_url=args.base_url, api_key=api_key)

    test_basic(client, args.model)
    test_json_schema(client, args.model)
    test_tools(client, args.model)
    if not args.no_stream:
        test_stream(client, args.model)


if __name__ == "__main__":
    main()
