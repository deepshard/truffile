import argparse
import base64
import contextlib
import json
import mimetypes
import os
import re
import select
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from .ui import C, MUSHROOM, SUPPORTED_SERVER_MIME_TYPES, MushroomPulse, error, success, info, warn
from .connect import _resolve_connected_device
from .models import _fetch_models_payload, _pick_model_interactive, _default_model

try:
    import readline
except Exception:
    readline = None

try:
    import termios
    import tty
except Exception:
    termios = None
    tty = None

DEFAULT_SYSTEM_PROMPT = None

REPL_COMMANDS = [
    "/help", "/", "/history", "/reset", "/models", "/config",
    "/reasoning", "/stream", "/json", "/tools", "/max_tokens",
    "/temperature", "/top_p", "/max_rounds", "/system", "/mcp",
    "/attach", "/exit", "/quit",
]

class ChatSettings:
    model: str
    system_prompt: str | None = DEFAULT_SYSTEM_PROMPT
    reasoning: bool = True
    stream: bool = True
    json_mode: bool = False
    max_tokens: int = 2048
    temperature: float | None = None
    top_p: float | None = None
    default_tools: bool = True
    max_tool_rounds: int = 8


class ChatMCPClient:
    def __init__(self) -> None:
        self._group: Any | None = None
        self.endpoint: str | None = None

    @property
    def connected(self) -> bool:
        return self._group is not None

    async def connect_streamable_http(self, endpoint: str) -> None:
        from mcp.client.session_group import ClientSessionGroup, StreamableHttpParameters

        await self.disconnect()
        group = ClientSessionGroup()
        await group.__aenter__()
        try:
            await group.connect_to_server(StreamableHttpParameters(url=endpoint))
        except Exception:
            with contextlib.suppress(Exception):
                await group.__aexit__(None, None, None)
            raise
        self._group = group
        self.endpoint = endpoint

    async def disconnect(self) -> None:
        if self._group is None:
            self.endpoint = None
            return
        group = self._group
        self._group = None
        self.endpoint = None
        with contextlib.suppress(Exception):
            await group.__aexit__(None, None, None)

    def list_tool_names(self) -> list[str]:
        if self._group is None:
            return []
        names: list[str] = []
        for _server_name, tool in self._group.list_tools():
            name = getattr(tool, "name", None)
            if isinstance(name, str):
                names.append(name)
        return sorted(set(names))

    def has_tool(self, name: str) -> bool:
        if self._group is None:
            return False
        try:
            tool = self._group.get_tool(name)
            return tool is not None
        except Exception:
            return False

    def build_openai_tools(self) -> list[dict[str, Any]]:
        if self._group is None:
            return []
        tools: list[dict[str, Any]] = []
        for _server_name, tool in self._group.list_tools():
            name = getattr(tool, "name", None)
            if not isinstance(name, str) or not name:
                continue
            description = str(getattr(tool, "description", "") or "")
            schema = getattr(tool, "inputSchema", None)
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            if schema.get("type") != "object":
                schema = {"type": "object", "properties": {}}
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": schema,
                    },
                }
            )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._group is None:
            return {"error": "mcp not connected"}
        try:
            result = await self._group.call_tool(name, arguments)
            content: list[dict[str, Any]] = []
            for part in result.content:
                if hasattr(part, "model_dump"):
                    content.append(part.model_dump())  # type: ignore[call-arg]
                elif isinstance(part, dict):
                    content.append(part)
                else:
                    content.append({"value": str(part)})
            return {
                "is_error": bool(result.isError),
                "structured_content": result.structuredContent,
                "content": content,
            }
        except Exception as exc:
            return {"error": "mcp call failed", "tool": name, "detail": str(exc)}


def _print_chat_config(settings: ChatSettings, mcp_client: ChatMCPClient) -> None:
    print(f"{C.BLUE}chat config{C.RESET}")
    print(f"  {C.DIM}model:{C.RESET} {settings.model}")
    print(f"  {C.DIM}reasoning:{C.RESET} {settings.reasoning}")
    print(f"  {C.DIM}stream:{C.RESET} {settings.stream}")
    print(f"  {C.DIM}json:{C.RESET} {settings.json_mode}")
    print(f"  {C.DIM}tools:{C.RESET} {settings.default_tools}")
    print(f"  {C.DIM}max_tokens:{C.RESET} {settings.max_tokens}")
    print(f"  {C.DIM}temperature:{C.RESET} {settings.temperature}")
    print(f"  {C.DIM}top_p:{C.RESET} {settings.top_p}")
    print(f"  {C.DIM}max_rounds:{C.RESET} {settings.max_tool_rounds}")
    print(f"  {C.DIM}system:{C.RESET} {settings.system_prompt or '<none>'}")
    print(f"  {C.DIM}mcp:{C.RESET} {mcp_client.endpoint or '<disconnected>'}")


def _parse_on_off(value: str) -> bool | None:
    v = value.strip().lower()
    if v in {"on", "true", "1", "yes"}:
        return True
    if v in {"off", "false", "0", "no"}:
        return False
    return None


def _resolve_image_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"image file not found: {path}")
    return path


def _guess_mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


def _normalize_image_for_server(image_bytes: bytes, mime: str) -> tuple[bytes, str, bool]:
    mime_l = mime.lower()
    if mime_l in SUPPORTED_SERVER_MIME_TYPES:
        return image_bytes, mime_l, False
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError(
            f"image mime {mime!r} is not supported by server decoder and Pillow is unavailable: {exc}"
        ) from exc

    from io import BytesIO

    try:
        with Image.open(BytesIO(image_bytes)) as im:
            rgb = im.convert("RGB")
            out = BytesIO()
            rgb.save(out, format="PNG")
            return out.getvalue(), "image/png", True
    except Exception as exc:
        raise RuntimeError(f"failed to transcode unsupported image mime {mime!r}: {exc}") from exc


def _resolve_image_bytes_and_mime(image_path_or_url: str) -> tuple[bytes, str, str]:
    if image_path_or_url.startswith("http://") or image_path_or_url.startswith("https://"):
        with httpx.Client(timeout=60.0) as client:
            resp = client.get(image_path_or_url)
            resp.raise_for_status()
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            mime = content_type if content_type.startswith("image/") else "image/jpeg"
            size_kib = len(resp.content) / 1024.0
            image_bytes, mime, transcoded = _normalize_image_for_server(resp.content, mime)
            desc = f"url={image_path_or_url} size={size_kib:.1f} KiB mime={mime}"
            if transcoded:
                desc += " (transcoded)"
            return image_bytes, mime, desc

    path = _resolve_image_path(image_path_or_url)
    size_kib = path.stat().st_size / 1024.0
    mime = _guess_mime_type(path)
    image_bytes, mime, transcoded = _normalize_image_for_server(path.read_bytes(), mime)
    desc = f"path={path} size={size_kib:.1f} KiB mime={mime}"
    if transcoded:
        desc += " (transcoded)"
    return image_bytes, mime, desc


def _to_data_url(image_bytes: bytes, mime: str) -> str:
    payload = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _make_user_message(text: str, image_data_url: str | None) -> dict[str, Any]:
    if image_data_url is None:
        return {"role": "user", "content": text}
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ],
    }


def _build_default_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for a query and return top results.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query."},
                        "max_results": {
                            "type": "integer",
                            "description": "Number of results to return (1-10).",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description": "Fetch and extract readable text from a URL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Absolute http/https URL."},
                        "max_chars": {
                            "type": "integer",
                            "description": "Max number of characters to return (500-20000).",
                            "default": 8000,
                        },
                    },
                    "required": ["url"],
                },
            },
        },
    ]


def _tool_web_search(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", "")).strip()
    if not query:
        return {"error": "query is required"}
    max_results = arguments.get("max_results", 5)
    try:
        max_results = int(max_results)
    except (TypeError, ValueError):
        max_results = 5
    max_results = max(1, min(max_results, 10))
    try:
        from ddgs import DDGS
    except Exception as exc:
        return {
            "error": "ddgs is not installed or failed to import",
            "detail": str(exc),
            "hint": "pip install ddgs",
        }
    rows: list[dict[str, Any]] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                if len(rows) >= max_results:
                    break
                rows.append(
                    {
                        "title": r.get("title"),
                        "url": r.get("href") or r.get("url"),
                        "snippet": r.get("body") or r.get("snippet"),
                    }
                )
    except Exception as exc:
        return {"error": "web_search failed", "detail": str(exc)}
    return {"query": query, "count": len(rows), "results": rows}


def _tool_web_fetch(arguments: dict[str, Any]) -> dict[str, Any]:
    url = str(arguments.get("url", "")).strip()
    if not url:
        return {"error": "url is required"}
    max_chars = arguments.get("max_chars", 8000)
    try:
        max_chars = int(max_chars)
    except (TypeError, ValueError):
        max_chars = 8000
    max_chars = max(500, min(max_chars, 20000))
    try:
        import trafilatura
    except Exception as exc:
        return {
            "error": "trafilatura is not installed or failed to import",
            "detail": str(exc),
            "hint": "pip install trafilatura",
        }
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return {"error": "failed to download url", "url": url}
        text = trafilatura.extract(downloaded, include_links=False, include_images=False)
        if not text:
            return {"error": "failed to extract readable text", "url": url}
        text = text.strip()
        truncated = len(text) > max_chars
        return {
            "url": url,
            "content": text[:max_chars],
            "truncated": truncated,
            "content_chars": min(len(text), max_chars),
        }
    except Exception as exc:
        return {"error": "web_fetch failed", "url": url, "detail": str(exc)}


def _execute_default_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "web_search":
        return _tool_web_search(arguments)
    if name == "web_fetch":
        return _tool_web_fetch(arguments)
    return {"error": f"unknown tool '{name}'"}


def _print_history(messages: list[dict[str, Any]]) -> None:
    for idx, msg in enumerate(messages):
        role = str(msg.get("role", "unknown"))
        if role == "assistant" and msg.get("tool_calls"):
            text = f"[tool_calls={len(msg.get('tool_calls') or [])}]"
        else:
            content = msg.get("content", "")
            if isinstance(content, list):
                text = json.dumps(content, ensure_ascii=True)
            else:
                text = str(content)
            text = text.replace("\n", " ")
            if len(text) > 160:
                text = text[:157] + "..."
        print(f"{idx:03d} {role:9s} {text}")


def _build_chat_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    settings: ChatSettings,
    stream: bool,
    tools: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "reasoning": {"enabled": bool(settings.reasoning)},
        "max_tokens": int(settings.max_tokens),
    }
    if settings.temperature is not None:
        body["temperature"] = settings.temperature
    if settings.top_p is not None:
        body["top_p"] = settings.top_p
    if stream:
        body["stream_options"] = {"include_usage": True}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    return body


def _print_reasoning_and_response(reasoning_text: str, response_text: str, show_reasoning: bool) -> None:
    if show_reasoning and reasoning_text:
        print(f"{C.GRAY}thinking:{C.RESET}")
        print(f"{C.GRAY}{reasoning_text}{C.RESET}")
        if response_text:
            print()
    if response_text:
        print(response_text)


def _print_repl_commands(prefix: str | None = None) -> None:
    command_pool = [cmd for cmd in REPL_COMMANDS if cmd != "/"]
    if prefix is None:
        matches = command_pool
    else:
        matches = [cmd for cmd in command_pool if cmd.startswith(prefix)]
    if not matches:
        print(f"{C.YELLOW}no command matches: {prefix}{C.RESET}")
        return
    rendered = ", ".join(f"{C.BLUE}{cmd}{C.RESET}" for cmd in matches)
    print(f"commands: {rendered}")


def _install_repl_completer(commands: list[str]) -> Callable[[], None] | None:
    if readline is None:
        return None
    try:
        prev_completer = readline.get_completer()
        prev_delims = readline.get_completer_delims()
        prev_display_hook = getattr(readline, "get_completion_display_matches_hook", lambda: None)()
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set show-all-if-ambiguous on")
        readline.parse_and_bind("set show-all-if-unmodified on")
        readline.parse_and_bind("set completion-ignore-case on")
        readline.set_completer_delims(" \t\n")
        matches: list[str] = []

        def _complete(text: str, state: int) -> str | None:
            nonlocal matches
            if state == 0:
                buffer = readline.get_line_buffer().lstrip()
                if buffer.startswith("/"):
                    prefix = buffer.split()[0]
                    command_pool = [cmd for cmd in commands if cmd != "/"]
                    if prefix == "/":
                        matches = command_pool
                    else:
                        matches = [cmd for cmd in command_pool if cmd.startswith(prefix)]
                else:
                    matches = []
            if state < len(matches):
                return matches[state]
            return None

        readline.set_completer(_complete)
        if hasattr(readline, "set_completion_display_matches_hook"):
            def _display_matches(substitution: str, display_matches: list[str], longest_match_length: int) -> None:
                del substitution, longest_match_length
                if not display_matches:
                    return
                print()
                rendered = ", ".join(f"{C.BLUE}{cmd}{C.RESET}" for cmd in display_matches)
                print(f"commands: {rendered}")
                try:
                    readline.redisplay()
                except Exception:
                    pass
            readline.set_completion_display_matches_hook(_display_matches)

        def _cleanup() -> None:
            try:
                readline.set_completer(prev_completer)
                readline.set_completer_delims(prev_delims)
                if hasattr(readline, "set_completion_display_matches_hook"):
                    readline.set_completion_display_matches_hook(prev_display_hook)
            except Exception:
                pass

        return _cleanup
    except Exception:
        return None


class StreamAbortWatcher:
    def __init__(self) -> None:
        self.enabled = bool(sys.stdin.isatty() and termios is not None and tty is not None)
        self._fd: int | None = None
        self._old_attrs: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._abort_reason: str | None = None

    def __enter__(self) -> "StreamAbortWatcher":
        if not self.enabled:
            return self
        try:
            self._fd = sys.stdin.fileno()
            self._old_attrs = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        except Exception:
            self.enabled = False
            return self
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()
        return self

    def _watch(self) -> None:
        if self._fd is None:
            return
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([self._fd], [], [], 0.1)
            except Exception:
                return
            if not ready:
                continue
            try:
                ch = os.read(self._fd, 1)
            except Exception:
                continue
            if not ch:
                continue
            if ch == b"\x1b":
                self._abort_reason = "esc"
                self._stop.set()
                return

    def aborted(self) -> bool:
        return self._abort_reason is not None

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.2)
        if self.enabled and self._fd is not None and self._old_attrs is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)
            except Exception:
                pass
        return False


def _run_single_chat_request(
    *,
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    settings: ChatSettings,
    stream: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
    wait_anim = MushroomPulse("thinking")
    wait_anim.start()
    if stream:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        usage: dict[str, Any] | None = None
        tool_calls_by_index: dict[int, dict[str, Any]] = {}
        reasoning_stream_started = False
        interrupted = False
        first_event_seen = False

        try:
            with StreamAbortWatcher() as abort_watcher:
                with client.stream("POST", url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    for raw in resp.iter_lines():
                        if abort_watcher.aborted():
                            interrupted = True
                            break
                        if not raw:
                            continue
                        line = raw.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            evt = json.loads(data)
                        except Exception:
                            continue
                        if not first_event_seen:
                            wait_anim.stop()
                            first_event_seen = True

                        if isinstance(evt.get("usage"), dict):
                            usage = evt.get("usage")

                        choices = evt.get("choices")
                        if not isinstance(choices, list) or not choices:
                            continue
                        c0 = choices[0]
                        if not isinstance(c0, dict):
                            continue
                        delta = c0.get("delta", {})
                        if not isinstance(delta, dict):
                            continue

                        reasoning_chunk = delta.get("reasoning")
                        if isinstance(reasoning_chunk, str) and reasoning_chunk:
                            reasoning_parts.append(reasoning_chunk)
                            if settings.reasoning:
                                if not reasoning_stream_started:
                                    print(f"{C.GRAY}thinking:{C.RESET}")
                                    reasoning_stream_started = True
                                print(f"{C.GRAY}{reasoning_chunk}{C.RESET}", end="", flush=True)

                        content_chunk = delta.get("content")
                        if isinstance(content_chunk, str) and content_chunk:
                            content_parts.append(content_chunk)
                            print(content_chunk, end="", flush=True)

                        for tc in delta.get("tool_calls") or []:
                            if not isinstance(tc, dict):
                                continue
                            idx = tc.get("index")
                            if not isinstance(idx, int):
                                idx = len(tool_calls_by_index)
                            entry = tool_calls_by_index.setdefault(
                                idx,
                                {
                                    "id": tc.get("id", ""),
                                    "type": tc.get("type", "function"),
                                    "function": {"name": "", "arguments": ""},
                                },
                            )
                            if tc.get("id"):
                                entry["id"] = tc["id"]
                            if tc.get("type"):
                                entry["type"] = tc["type"]
                            fn = tc.get("function") or {}
                            if isinstance(fn, dict):
                                if fn.get("name"):
                                    entry["function"]["name"] += str(fn["name"])
                                if fn.get("arguments"):
                                    entry["function"]["arguments"] += str(fn["arguments"])
        except KeyboardInterrupt:
            interrupted = True
        finally:
            wait_anim.stop()

        msg: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts).strip()}
        reasoning_text = "".join(reasoning_parts).strip()
        if reasoning_text:
            msg["reasoning_content"] = reasoning_text
        if tool_calls_by_index:
            msg["tool_calls"] = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)]
        if settings.reasoning:
            if reasoning_stream_started:
                print()
            response_text = str(msg.get("content") or "")
            if response_text:
                print()
                print(response_text)
        elif content_parts:
            print()
        if interrupted:
            print(f"{C.YELLOW}response interrupted{C.RESET}")
        return msg, usage, interrupted

    try:
        resp = client.post(url, headers=headers, json=payload, timeout=120.0)
        resp.raise_for_status()
        body = resp.json()
    finally:
        wait_anim.stop()
    if settings.json_mode:
        print(json.dumps(body, indent=2))

    choices = body.get("choices", [])
    c0 = choices[0] if isinstance(choices, list) and choices else {}
    msg = c0.get("message", {}) if isinstance(c0, dict) else {}
    if not isinstance(msg, dict):
        msg = {}
    out: dict[str, Any] = {"role": "assistant", "content": str(msg.get("content", "") or "")}
    if isinstance(msg.get("reasoning"), str) and msg.get("reasoning"):
        out["reasoning_content"] = msg["reasoning"]
    if isinstance(msg.get("tool_calls"), list):
        out["tool_calls"] = msg.get("tool_calls")

    _print_reasoning_and_response(
        str(out.get("reasoning_content") or ""),
        str(out.get("content") or ""),
        bool(settings.reasoning),
    )
    return out, body.get("usage") if isinstance(body.get("usage"), dict) else None, False


async def _run_chat_turn(
    *,
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    model: str,
    settings: ChatSettings,
    mcp_client: ChatMCPClient,
    messages: list[dict[str, Any]],
    user_message: dict[str, Any],
) -> int:
    messages.append(user_message)

    max_rounds = max(1, int(settings.max_tool_rounds))
    for _ in range(max_rounds):
        stream = settings.stream and not settings.json_mode
        tools: list[dict[str, Any]] = []
        if settings.default_tools:
            tools.extend(_build_default_tools())
        if mcp_client.connected:
            tools.extend(mcp_client.build_openai_tools())

        payload = _build_chat_payload(
            model=model,
            messages=messages,
            settings=settings,
            stream=stream,
            tools=tools or None,
        )
        assistant_msg, usage, interrupted = _run_single_chat_request(
            client=client, url=url, headers=headers, payload=payload, settings=settings, stream=stream
        )
        messages.append(assistant_msg)
        if isinstance(usage, dict):
            image_tokens = usage.get("image_tokens") or 0
            image_tokens_part = f", image: {image_tokens}" if image_tokens else ""
            image_tps_part = f", image tps: {usage.get('image_tokens_per_second') or ''}" if image_tokens else ""
            print(
                f"{C.DIM}[usage] tokens(prompt: {usage.get('prompt_tokens') or ''}, completion: {usage.get('completion_tokens') or ''}, total: {usage.get('total_tokens') or ''}{image_tokens_part}) usage(decode tps: {usage.get('decode_tokens_per_second') or ''}, prefill tps: {usage.get('prefill_tokens_per_second') or ''}{image_tps_part}) itl: {usage.get('itl_ms') or ''}ms ttft: {usage.get('ttft_ms') or ''}ms{C.RESET}"
            )
        if interrupted:
            return 130

        tool_calls = assistant_msg.get("tool_calls") if isinstance(assistant_msg, dict) else None
        if not tools or not isinstance(tool_calls, list) or not tool_calls:
            return 0

        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            fn = tool_call.get("function") or {}
            if not isinstance(fn, dict):
                continue
            name = str(fn.get("name") or "")
            raw_args = str(fn.get("arguments") or "{}")
            try:
                parsed_args = json.loads(raw_args)
            except json.JSONDecodeError:
                parsed_args = {"_raw": raw_args}
            if name in {"web_search", "web_fetch"}:
                print(f"{C.CYAN}{HAMMER} tool{C.RESET} {name}")
                tool_result = _execute_default_tool(name, parsed_args)
            elif mcp_client.has_tool(name):
                print(f"{C.CYAN}{HAMMER} mcp{C.RESET} {name}")
                tool_result = await mcp_client.call_tool(name, parsed_args)
            else:
                print(f"{C.YELLOW}{WARN} unknown tool{C.RESET} {name}")
                tool_result = {"error": f"unknown tool '{name}'"}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )

    warn("Reached max tool rounds without a final assistant response")
    return 1


async def cmd_chat(args, storage: StorageService) -> int:
    prompt_words = getattr(args, "prompt_words", None)
    prompt = " ".join(prompt_words).strip() if prompt_words else ""

    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return 1

    spinner = Spinner("Resolving default model")
    spinner.start()
    model = await _default_model(ip)
    if not model:
        spinner.fail("Failed to resolve default model from IF2")
        return 1
    spinner.stop(success=True)

    settings = ChatSettings(model=model)
    mcp_client = ChatMCPClient()
    messages: list[dict[str, Any]] = []
    pending_image_data_url: str | None = None
    pending_image_desc: str | None = None

    url = f"http://{ip}/if2/v1/chat/completions"
    headers = {"Content-Type": "application/json"}

    try:
        spinner = Spinner(f"Connecting to {device}")
        spinner.start()
        with httpx.Client(timeout=None) as client:
            spinner.stop(success=True)

            # REPL mode (default).
            print(f"{C.DIM}model: {settings.model}{C.RESET}")
            print(
                f"{C.DIM}commands: /help, /history, /reset, /models, /attach, /config, /mcp, /exit{C.RESET}"
            )

            cleanup_repl = _install_repl_completer(REPL_COMMANDS)
            try:
                if prompt:
                    print(f"{C.CYAN}> {prompt}{C.RESET}")
                    rc = await _run_chat_turn(
                        client=client,
                        url=url,
                        headers=headers,
                        model=settings.model,
                        settings=settings,
                        mcp_client=mcp_client,
                        messages=messages,
                        user_message=_make_user_message(prompt, pending_image_data_url),
                    )
                    if rc != 0:
                        if rc == 130:
                            return 0
                        else:
                            return rc
                    else:
                        pending_image_data_url = None
                        pending_image_desc = None

                while True:
                    try:
                        line = input(f"{C.CYAN}> {C.RESET}").strip()
                    except EOFError:
                        print()
                        return 0
                    except KeyboardInterrupt:
                        print()
                        return 0

                    if not line:
                        continue
                    if line in {"/", "/help"}:
                        _print_repl_commands()
                        continue
                    if line in {"/exit", "/quit"}:
                        return 0
                    if line == "/history":
                        _print_history(messages)
                        continue
                    if line == "/reset":
                        messages = []
                        if settings.system_prompt:
                            messages.append({"role": "system", "content": settings.system_prompt})
                        pending_image_data_url = None
                        pending_image_desc = None
                        print(f"{C.YELLOW}history reset (and cleared pending attachment){C.RESET}")
                        continue
                    if line in {"/models", "/model"}:
                        try:
                            models = _fetch_models_payload(client, ip)
                            selected_model = _pick_model_interactive(models, settings.model)
                            if selected_model and selected_model != settings.model:
                                settings.model = selected_model
                                print(f"{C.GREEN}{CHECK}{C.RESET} model switched: {settings.model}")
                        except Exception as exc:
                            error(f"failed to list models: {exc}")
                        continue
                    if line == "/config":
                        _print_chat_config(settings, mcp_client)
                        continue
                    if line.startswith("/reasoning"):
                        arg = line[len("/reasoning"):].strip()
                        if not arg:
                            print(f"{C.DIM}reasoning={settings.reasoning}{C.RESET}")
                            continue
                        val = _parse_on_off(arg)
                        if val is None:
                            warn("usage: /reasoning <on|off>")
                            continue
                        settings.reasoning = val
                        print(f"{C.GREEN}{CHECK}{C.RESET} reasoning={settings.reasoning}")
                        continue
                    if line.startswith("/stream"):
                        arg = line[len("/stream"):].strip()
                        if not arg:
                            print(f"{C.DIM}stream={settings.stream}{C.RESET}")
                            continue
                        val = _parse_on_off(arg)
                        if val is None:
                            warn("usage: /stream <on|off>")
                            continue
                        settings.stream = val
                        print(f"{C.GREEN}{CHECK}{C.RESET} stream={settings.stream}")
                        continue
                    if line.startswith("/json"):
                        arg = line[len("/json"):].strip()
                        if not arg:
                            print(f"{C.DIM}json={settings.json_mode}{C.RESET}")
                            continue
                        val = _parse_on_off(arg)
                        if val is None:
                            warn("usage: /json <on|off>")
                            continue
                        settings.json_mode = val
                        print(f"{C.GREEN}{CHECK}{C.RESET} json={settings.json_mode}")
                        continue
                    if line.startswith("/tools"):
                        arg = line[len("/tools"):].strip()
                        if not arg:
                            print(f"{C.DIM}tools={settings.default_tools}{C.RESET}")
                            continue
                        val = _parse_on_off(arg)
                        if val is None:
                            warn("usage: /tools <on|off>")
                            continue
                        settings.default_tools = val
                        print(f"{C.GREEN}{CHECK}{C.RESET} tools={settings.default_tools}")
                        continue
                    if line.startswith("/max_tokens"):
                        arg = line[len("/max_tokens"):].strip()
                        if not arg:
                            print(f"{C.DIM}max_tokens={settings.max_tokens}{C.RESET}")
                            continue
                        try:
                            settings.max_tokens = max(1, int(arg))
                            print(f"{C.GREEN}{CHECK}{C.RESET} max_tokens={settings.max_tokens}")
                        except ValueError:
                            warn("usage: /max_tokens <int>")
                        continue
                    if line.startswith("/temperature"):
                        arg = line[len("/temperature"):].strip()
                        if not arg:
                            print(f"{C.DIM}temperature={settings.temperature}{C.RESET}")
                            continue
                        if arg.lower() in {"off", "none"}:
                            settings.temperature = None
                            print(f"{C.GREEN}{CHECK}{C.RESET} temperature=None")
                            continue
                        try:
                            settings.temperature = float(arg)
                            print(f"{C.GREEN}{CHECK}{C.RESET} temperature={settings.temperature}")
                        except ValueError:
                            warn("usage: /temperature <float|off>")
                        continue
                    if line.startswith("/top_p"):
                        arg = line[len("/top_p"):].strip()
                        if not arg:
                            print(f"{C.DIM}top_p={settings.top_p}{C.RESET}")
                            continue
                        if arg.lower() in {"off", "none"}:
                            settings.top_p = None
                            print(f"{C.GREEN}{CHECK}{C.RESET} top_p=None")
                            continue
                        try:
                            settings.top_p = float(arg)
                            print(f"{C.GREEN}{CHECK}{C.RESET} top_p={settings.top_p}")
                        except ValueError:
                            warn("usage: /top_p <float|off>")
                        continue
                    if line.startswith("/max_rounds"):
                        arg = line[len("/max_rounds"):].strip()
                        if not arg:
                            print(f"{C.DIM}max_rounds={settings.max_tool_rounds}{C.RESET}")
                            continue
                        try:
                            settings.max_tool_rounds = max(1, int(arg))
                            print(f"{C.GREEN}{CHECK}{C.RESET} max_rounds={settings.max_tool_rounds}")
                        except ValueError:
                            warn("usage: /max_rounds <int>")
                        continue
                    if line.startswith("/system"):
                        arg = line[len("/system"):].strip()
                        if not arg:
                            print(f"{C.DIM}system={settings.system_prompt or '<none>'}{C.RESET}")
                            continue
                        if arg.lower() in {"off", "none", "clear"}:
                            settings.system_prompt = None
                            if messages and messages[0].get("role") == "system":
                                messages.pop(0)
                            print(f"{C.GREEN}{CHECK}{C.RESET} system prompt cleared")
                            continue
                        settings.system_prompt = arg
                        if messages and messages[0].get("role") == "system":
                            messages[0]["content"] = arg
                        else:
                            messages.insert(0, {"role": "system", "content": arg})
                        print(f"{C.GREEN}{CHECK}{C.RESET} system prompt updated")
                        continue
                    if line.startswith("/mcp"):
                        parts = line.split(maxsplit=2)
                        if len(parts) == 1 or parts[1] == "status":
                            print(
                                f"{C.BLUE}/mcp status{C.RESET} "
                                f"{C.DIM}mcp={mcp_client.endpoint or '<disconnected>'} "
                                f"tools={len(mcp_client.list_tool_names())}{C.RESET}"
                            )
                            print(
                                f"{C.DIM}subcommands:{C.RESET} "
                                f"{C.BLUE}/mcp connect <url>{C.RESET}, "
                                f"{C.BLUE}/mcp tools{C.RESET}, "
                                f"{C.BLUE}/mcp disconnect{C.RESET}"
                            )
                            continue
                        sub = parts[1].lower()
                        if sub == "connect":
                            if len(parts) < 3:
                                warn("usage: /mcp connect <streamable-http-url>")
                                continue
                            endpoint = parts[2].strip()
                            if not endpoint.startswith(("http://", "https://")):
                                warn("mcp endpoint must start with http:// or https://")
                                continue
                            try:
                                await mcp_client.connect_streamable_http(endpoint)
                                print(
                                    f"{C.BLUE}/mcp connect{C.RESET} "
                                    f"{C.GREEN}{CHECK}{C.RESET} {endpoint} "
                                    f"({len(mcp_client.list_tool_names())} tools)"
                                )
                            except Exception as exc:
                                error(f"mcp connect failed: {exc}")
                            continue
                        if sub == "disconnect":
                            await mcp_client.disconnect()
                            print(f"{C.BLUE}/mcp disconnect{C.RESET} {C.GREEN}{CHECK}{C.RESET}")
                            continue
                        if sub == "tools":
                            names = mcp_client.list_tool_names()
                            if not names:
                                print(f"{C.BLUE}/mcp tools{C.RESET} {C.DIM}no tools available{C.RESET}")
                            else:
                                print(f"{C.BLUE}/mcp tools{C.RESET} {', '.join(names)}")
                            continue
                        warn("usage: /mcp <connect|disconnect|status|tools>")
                        continue
                    if line.startswith("/attach"):
                        parts = line.split(maxsplit=1)
                        if len(parts) != 2 or not parts[1].strip():
                            warn("usage: /attach <path-or-url>")
                            continue
                        src = parts[1].strip()
                        try:
                            image_bytes, mime, desc = _resolve_image_bytes_and_mime(src)
                            pending_image_data_url = _to_data_url(image_bytes, mime)
                            pending_image_desc = desc
                            print(f"{C.GREEN}{CHECK}{C.RESET} attachment ready: {desc}")
                        except FileNotFoundError as exc:
                            error(str(exc))
                        except httpx.HTTPError as exc:
                            error(f"failed to fetch image: {exc}")
                        except RuntimeError as exc:
                            error(str(exc))
                        continue
                    if line.startswith("/"):
                        matches = [cmd for cmd in REPL_COMMANDS if cmd.startswith(line)]
                        if matches:
                            _print_repl_commands(line)
                        else:
                            warn(f"unknown command: {line}")
                            _print_repl_commands()
                        continue

                    if pending_image_data_url is not None:
                        print(f"{C.MAGENTA}[attach]{C.RESET} sending with image: {pending_image_desc}")
                    rc = await _run_chat_turn(
                        client=client,
                        url=url,
                        headers=headers,
                        model=settings.model,
                        settings=settings,
                        mcp_client=mcp_client,
                        messages=messages,
                        user_message=_make_user_message(line, pending_image_data_url),
                    )
                    if rc != 0:
                        if rc == 130:
                            return 0
                        return rc
                    pending_image_data_url = None
                    pending_image_desc = None
            finally:
                if cleanup_repl:
                    cleanup_repl()
                await mcp_client.disconnect()
        return 0
    except Exception as e:
        try:
            spinner.fail(f"Chat request failed: {e}")  # type: ignore[name-defined]
        except Exception:
            error(f"Chat request failed: {e}")
        return 1


