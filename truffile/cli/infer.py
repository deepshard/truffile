import argparse
import base64
import contextlib
import json
import mimetypes
import re
import shutil
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from .ui import C, MUSHROOM, CHECK, HAMMER, WARN, SUPPORTED_SERVER_MIME_TYPES, Spinner, StreamAbortWatcher, error, success, info, warn, create_thinking_orb
from .connect import _resolve_connected_device
from .models import _fetch_models_payload, _pick_model_interactive, _default_model
from .commands import INFER_COMMANDS
from .prompt import TrufflePrompt
from .markdown import has_markdown, render_markdown, count_terminal_lines
from .art import ParticleOrb
from .welcome import show_infer_welcome
from truffile.storage import StorageService


DEFAULT_SYSTEM_PROMPT = None

@dataclass
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
        return sorted(self._group.tools.keys())

    def has_tool(self, name: str) -> bool:
        if self._group is None:
            return False
        return name in self._group.tools

    def build_openai_tools(self) -> list[dict[str, Any]]:
        if self._group is None:
            return []
        tools: list[dict[str, Any]] = []
        for name, tool in self._group.tools.items():
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
                    content.append(part.model_dump())
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


def _print_usage(usage: dict[str, Any]) -> None:
    prompt_t = usage.get("prompt_tokens", "")
    comp_t = usage.get("completion_tokens", "")
    total_t = usage.get("total_tokens", "")
    decode_tps = usage.get("decode_tokens_per_second", "")
    ttft = usage.get("ttft_ms", "")
    itl = usage.get("itl_ms", "")
    image_t = usage.get("image_tokens") or 0
    parts = [f"tokens {C.DIM}[{prompt_t}/{comp_t}/{total_t}]{C.RESET}"]
    if decode_tps:
        parts.append(f"decode {C.DIM}{decode_tps} t/s{C.RESET}")
    if ttft:
        parts.append(f"ttft {C.DIM}{ttft}ms{C.RESET}")
    if itl:
        parts.append(f"itl {C.DIM}{itl}ms{C.RESET}")
    if image_t:
        parts.append(f"image {C.DIM}{image_t}t{C.RESET}")
    sep = f" {C.DIM}|{C.RESET} "
    print(f"\n{C.DIM}---{C.RESET}")
    print(sep.join(parts))


def _print_infer_help() -> None:
    print(f"\n{C.BOLD}commands:{C.RESET}")
    for sc in INFER_COMMANDS:
        display = f"{sc.name} {sc.arg_hint}" if sc.arg_hint else sc.name
        print(f"  {C.CYAN}{display}{C.RESET} — {sc.description}")
    print(f"\n{C.DIM}alt+enter for newline · tab to complete commands · ctrl+d to exit{C.RESET}\n")


def _run_single_chat_request(
    *,
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    settings: ChatSettings,
    stream: bool,
    quiet: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
    orb = None if quiet else create_thinking_orb()
    if orb is not None:
        orb.start(ParticleOrb.STATE_ACTIVE)
    orb_stopped = quiet
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
                            # stop orb before first visible output
                            if not orb_stopped and orb is not None:
                                orb.stop()
                                orb_stopped = True
                            reasoning_parts.append(reasoning_chunk)
                            if settings.reasoning and not quiet:
                                if not reasoning_stream_started:
                                    print(f"{C.GRAY}thinking:{C.RESET}")
                                    reasoning_stream_started = True
                                print(f"{C.GRAY}{reasoning_chunk}{C.RESET}", end="", flush=True)

                        content_chunk = delta.get("content")
                        if isinstance(content_chunk, str) and content_chunk:
                            # stop orb before first visible output
                            if not orb_stopped and orb is not None:
                                orb.stop()
                                orb_stopped = True
                            content_parts.append(content_chunk)
                            if not quiet:
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
            if not orb_stopped and orb is not None:
                orb.stop()
                orb_stopped = True

        msg: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts).strip()}
        reasoning_text = "".join(reasoning_parts).strip()
        if reasoning_text:
            msg["reasoning_content"] = reasoning_text
        if tool_calls_by_index:
            msg["tool_calls"] = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)]
        full_content = "".join(content_parts).strip()
        # content was already streamed to stdout chunk by chunk
        if not quiet and (reasoning_stream_started or content_parts):
            print()

        # markdown re-render: clear raw streamed content, replace with rich formatted
        if not quiet and full_content and has_markdown(full_content):
            try:
                width = shutil.get_terminal_size().columns
                # only clear the content lines (not reasoning which was above)
                lines_to_clear = count_terminal_lines(full_content, width) + 1
                render_markdown(full_content, lines_to_clear)
            except Exception:
                pass
        if interrupted and not quiet:
            print(f"{C.YELLOW}response interrupted{C.RESET}")
        return msg, usage, interrupted

    try:
        resp = client.post(url, headers=headers, json=payload, timeout=120.0)
        resp.raise_for_status()
        body = resp.json()
    finally:
        if not orb_stopped and orb is not None:
            orb.stop()
            orb_stopped = True
    if settings.json_mode and not quiet:
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

    if not quiet:
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
    quiet: bool = False,
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
            client=client, url=url, headers=headers, payload=payload, settings=settings, stream=stream, quiet=quiet
        )
        messages.append(assistant_msg)
        if isinstance(usage, dict) and not quiet:
            _print_usage(usage)
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
                if not quiet:
                    print(f"{C.CYAN}{HAMMER} tool{C.RESET} {name}")
                else:
                    sys.stderr.write(f"{HAMMER} tool {name}\n")
                tool_result = _execute_default_tool(name, parsed_args)
            elif mcp_client.has_tool(name):
                if not quiet:
                    print(f"{C.CYAN}{HAMMER} mcp{C.RESET} {name}")
                else:
                    sys.stderr.write(f"{HAMMER} mcp {name}\n")
                tool_result = await mcp_client.call_tool(name, parsed_args)
            else:
                if not quiet:
                    print(f"{C.YELLOW}{WARN} unknown tool{C.RESET} {name}")
                else:
                    sys.stderr.write(f"{WARN} unknown tool {name}\n")
                tool_result = {"error": f"unknown tool '{name}'"}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )

    if quiet:
        sys.stderr.write("Reached max tool rounds without a final assistant response\n")
    else:
        warn("Reached max tool rounds without a final assistant response")
    return 1


def _is_oneshot_invocation(args) -> bool:
    if getattr(args, "list_models", False):
        return True
    if getattr(args, "list_tools", False):
        return True
    if getattr(args, "call", None):
        return True
    if getattr(args, "prompt_file", None):
        return True
    if getattr(args, "stdin", False):
        return True
    prompt_words = getattr(args, "prompt_words", None)
    if prompt_words:
        return True
    # piped stdin auto-detects to one-shot
    if not sys.stdin.isatty():
        return True
    return False


def _eprint_factory(quiet: bool) -> Callable[[str], None]:
    if quiet:
        return lambda _msg: None
    def _eprint(msg: str) -> None:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    return _eprint


def _read_prompt_from_args(args) -> str:
    parts: list[str] = []
    prompt_words = getattr(args, "prompt_words", None) or []
    if prompt_words:
        parts.append(" ".join(prompt_words).strip())
    prompt_file = getattr(args, "prompt_file", None)
    if prompt_file:
        path = Path(prompt_file).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"--prompt-file not found: {path}")
        parts.append(path.read_text(encoding="utf-8").strip())
    use_stdin = bool(getattr(args, "stdin", False)) or (
        not sys.stdin.isatty() and not prompt_words and not prompt_file
    )
    if use_stdin:
        try:
            data = sys.stdin.read()
        except Exception:
            data = ""
        if data:
            parts.append(data.strip())
    return "\n\n".join(p for p in parts if p)


def _apply_settings_overrides(args, settings: ChatSettings) -> None:
    if getattr(args, "system", None) is not None:
        settings.system_prompt = args.system
    if getattr(args, "temperature", None) is not None:
        settings.temperature = float(args.temperature)
    if getattr(args, "top_p", None) is not None:
        settings.top_p = float(args.top_p)
    if getattr(args, "max_tokens", None) is not None:
        settings.max_tokens = max(1, int(args.max_tokens))
    if getattr(args, "max_rounds", None) is not None:
        settings.max_tool_rounds = max(1, int(args.max_rounds))
    if getattr(args, "reasoning", None) is not None:
        settings.reasoning = args.reasoning == "on"
    if getattr(args, "no_default_tools", False) or getattr(args, "no_tools", False):
        settings.default_tools = False
    if getattr(args, "json", False):
        settings.json_mode = True
    if getattr(args, "force_stream", False):
        settings.stream = True
    if getattr(args, "no_stream", False):
        settings.stream = False


def _resolve_oneshot_images(args, eprint: Callable[[str], None]) -> list[str]:
    raw_images = getattr(args, "image", None) or []
    out: list[str] = []
    for src in raw_images:
        image_bytes, mime, desc = _resolve_image_bytes_and_mime(src)
        out.append(_to_data_url(image_bytes, mime))
        eprint(f"{CHECK} attached image: {desc}")
    return out


def _make_user_message_multi(text: str, image_data_urls: list[str]) -> dict[str, Any]:
    if not image_data_urls:
        return {"role": "user", "content": text}
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for url in image_data_urls:
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return {"role": "user", "content": parts}


async def _connect_oneshot_mcp(args, eprint: Callable[[str], None]) -> ChatMCPClient:
    """Connect to all --mcp endpoints. Caller must close()."""
    mcp_client = ChatMCPClient()
    endpoints = getattr(args, "mcp", None) or []
    for endpoint in endpoints:
        endpoint = endpoint.strip()
        if not endpoint.startswith(("http://", "https://")):
            raise RuntimeError(f"--mcp endpoint must start with http:// or https://: {endpoint}")
        eprint(f"connecting to mcp: {endpoint}")
        await mcp_client.connect_streamable_http(endpoint)
        eprint(f"{CHECK} mcp connected: {endpoint} ({len(mcp_client.list_tool_names())} tools)")
    return mcp_client


async def _run_oneshot(args, storage: StorageService) -> int:
    quiet = bool(getattr(args, "quiet", False))
    eprint = _eprint_factory(quiet)
    json_out = bool(getattr(args, "json", False))

    # device + IP
    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return 1

    # --list-models: short circuit, no model resolution
    if getattr(args, "list_models", False):
        with httpx.Client(timeout=getattr(args, "timeout", None) or 30.0) as http:
            try:
                models = _fetch_models_payload(http, ip)
            except Exception as exc:
                eprint(f"failed to list models: {exc}")
                return 1
        if json_out:
            print(json.dumps({"models": models}, indent=2))
        else:
            for m in models:
                name = m.get("name") or m.get("id") or "<unnamed>"
                print(name)
        return 0

    # resolve model
    requested_model = getattr(args, "model", None)
    if requested_model:
        model = requested_model
    else:
        eprint(f"resolving default model on {device}")
        model = await _default_model(ip)
        if not model:
            eprint("failed to resolve default model from IF2")
            return 1

    settings = ChatSettings(model=model)
    # in one-shot mode, default to non-streaming for clean stdout capture.
    settings.stream = False
    _apply_settings_overrides(args, settings)

    timeout = getattr(args, "timeout", None)
    http_timeout: Any = timeout if timeout else None

    url = f"http://{ip}/if2/v1/chat/completions"
    from .in_container import in_container_http_headers
    headers = {"Content-Type": "application/json", **in_container_http_headers()}

    mcp_client: ChatMCPClient | None = None
    try:
        try:
            mcp_client = await _connect_oneshot_mcp(args, eprint)
        except Exception as exc:
            eprint(f"mcp connect failed: {exc}")
            return 1

        # --list-tools: print built-ins + any MCP tools, exit
        if getattr(args, "list_tools", False):
            built_ins = ["web_search", "web_fetch"] if settings.default_tools else []
            mcp_tools = mcp_client.list_tool_names()
            if json_out:
                print(json.dumps({"built_in": built_ins, "mcp": mcp_tools}, indent=2))
            else:
                for name in built_ins:
                    print(f"built-in:{name}")
                for name in mcp_tools:
                    print(f"mcp:{name}")
            return 0

        # --call <tool>: one-off invocation
        call_tool = getattr(args, "call", None)
        if call_tool:
            raw_args = getattr(args, "tool_args", None) or "{}"
            try:
                parsed_args = json.loads(raw_args)
            except json.JSONDecodeError as exc:
                eprint(f"--tool-args is not valid JSON: {exc}")
                return 1
            if not isinstance(parsed_args, dict):
                eprint("--tool-args must be a JSON object")
                return 1
            if call_tool in {"web_search", "web_fetch"} and settings.default_tools:
                result = _execute_default_tool(call_tool, parsed_args)
            elif mcp_client.has_tool(call_tool):
                result = await mcp_client.call_tool(call_tool, parsed_args)
            else:
                eprint(f"unknown tool: {call_tool} (use --list-tools to see available)")
                return 1
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if not (isinstance(result, dict) and (result.get("error") or result.get("is_error"))) else 1

        # prompt path
        try:
            prompt = _read_prompt_from_args(args)
        except FileNotFoundError as exc:
            eprint(str(exc))
            return 1
        if not prompt:
            eprint("no prompt provided (positional, --prompt-file, or stdin required)")
            return 1

        try:
            image_urls = _resolve_oneshot_images(args, eprint)
        except FileNotFoundError as exc:
            eprint(str(exc))
            return 1
        except Exception as exc:
            eprint(f"failed to attach image: {exc}")
            return 1

        messages: list[dict[str, Any]] = []
        if settings.system_prompt:
            messages.append({"role": "system", "content": settings.system_prompt})

        # we always run quiet inside the helpers and format ourselves below
        with httpx.Client(timeout=http_timeout) as http:
            user_message = _make_user_message_multi(prompt, image_urls)
            rc = await _run_chat_turn(
                client=http,
                url=url,
                headers=headers,
                model=settings.model,
                settings=settings,
                mcp_client=mcp_client,
                messages=messages,
                user_message=user_message,
                quiet=True,
            )
        if rc == 130:
            eprint("interrupted")
            return 130
        if rc != 0:
            return rc

        # find the final assistant message
        final_assistant: dict[str, Any] | None = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                final_assistant = msg
                break

        content = str((final_assistant or {}).get("content") or "")
        reasoning = str((final_assistant or {}).get("reasoning_content") or "")
        tool_calls = (final_assistant or {}).get("tool_calls") or []

        if json_out:
            payload = {
                "model": settings.model,
                "device": device,
                "content": content,
                "reasoning": reasoning or None,
                "tool_calls": tool_calls or None,
                "messages": messages,
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            if getattr(args, "show_reasoning", False) and reasoning:
                sys.stderr.write("--- reasoning ---\n")
                sys.stderr.write(reasoning + "\n")
                sys.stderr.write("--- end reasoning ---\n")
            print(content)
        return 0
    finally:
        if mcp_client is not None:
            with contextlib.suppress(Exception):
                await mcp_client.disconnect()


async def cmd_infer(args, storage: StorageService) -> int:
    if _is_oneshot_invocation(args):
        return await _run_oneshot(args, storage)

    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return 1

    requested_model = getattr(args, "model", None)
    if requested_model:
        model = requested_model
    else:
        spinner = Spinner("Resolving default model")
        spinner.start()
        model = await _default_model(ip)
        if not model:
            spinner.fail("Failed to resolve default model from IF2")
            return 1
        spinner.stop(success=True)

    settings = ChatSettings(model=model)
    # apply CLI overrides so the REPL inherits user-provided defaults
    _apply_settings_overrides(args, settings)
    mcp_client = ChatMCPClient()
    messages: list[dict[str, Any]] = []
    if settings.system_prompt:
        messages.append({"role": "system", "content": settings.system_prompt})
    pending_image_data_url: str | None = None
    pending_image_desc: str | None = None
    # preload first --image as the pending attachment for the next user turn
    raw_images = getattr(args, "image", None) or []
    if raw_images:
        try:
            image_bytes, mime, desc = _resolve_image_bytes_and_mime(raw_images[0])
            pending_image_data_url = _to_data_url(image_bytes, mime)
            pending_image_desc = desc
        except Exception as exc:
            error(f"failed to attach image: {exc}")
            return 1

    url = f"http://{ip}/if2/v1/chat/completions"
    from .in_container import in_container_http_headers
    headers = {"Content-Type": "application/json", **in_container_http_headers()}

    try:
        spinner = Spinner(f"Connecting to {device}")
        spinner.start()
        with httpx.Client(timeout=None) as client:
            spinner.stop(success=True)

            # auto-connect any --mcp endpoints
            for endpoint in (getattr(args, "mcp", None) or []):
                endpoint = endpoint.strip()
                if not endpoint.startswith(("http://", "https://")):
                    error(f"--mcp endpoint must start with http:// or https://: {endpoint}")
                    return 1
                try:
                    await mcp_client.connect_streamable_http(endpoint)
                    print(f"{C.GREEN}{CHECK}{C.RESET} mcp connected: {endpoint} ({len(mcp_client.list_tool_names())} tools)")
                except Exception as exc:
                    error(f"mcp connect failed: {exc}")
                    return 1

            # REPL mode
            show_infer_welcome(model=settings.model, device=device)
            if pending_image_desc:
                print(f"{C.MAGENTA}[attach]{C.RESET} pending image: {pending_image_desc}")

            prompt_ui = TrufflePrompt("> ", INFER_COMMANDS)
            try:
                while True:
                    raw = await prompt_ui.get_input()
                    if raw is None:
                        print(f"\n{MUSHROOM} goodbye!")
                        return 0
                    line = raw.strip()
                    if not line:
                        continue
                    if line in {"/", "/help"}:
                        _print_infer_help()
                        continue
                    if line in {"/exit", "/quit"}:
                        print(f"{MUSHROOM} goodbye!")
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
                    if line.startswith("/create"):
                        from .create import cmd_create
                        from types import SimpleNamespace
                        create_arg = line[len("/create"):].strip() or None
                        cmd_create(SimpleNamespace(name=create_arg, path=None))
                        continue
                    if line.startswith("/"):
                        warn(f"unknown command: {line}. type /help")
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
                await mcp_client.disconnect()
        return 0
    except Exception as e:
        try:
            spinner.fail(f"Chat request failed: {e}")  # type: ignore[name-defined]
        except Exception:
            error(f"Chat request failed: {e}")
        return 1


