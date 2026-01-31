#!/usr/bin/env python3
"""Minimal OpenAI-compatible /v1/chat/completions proxy for Truffle gRPC inference."""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

import grpc

from .common import THINK_TAGS, clean_response
from .prompts import (
    TOOL_TAGS,
    AgentPromptBuilder,
    _build_tool_call_response_format,
    _build_tool_call_response_format_non_reasoning,
)
from .tooling import Tool

from truffle.infer.convo.conversation_pb2 import Conversation, Message
from truffle.infer.finishreason_pb2 import FinishReason
from truffle.infer.gencfg_pb2 import ResponseFormat
from truffle.infer.irequest_pb2 import IRequest
from truffle.infer.infer_pb2_grpc import InferenceServiceStub
from truffle.infer.model_pb2 import GetModelListRequest, Model


_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: Dict[str, Model] = {}
_MODEL_LIST: List[Model] = []


def _now_ts() -> int:
    return int(time.time())


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _load_models(stub: InferenceServiceStub) -> None:
    global _MODEL_CACHE, _MODEL_LIST
    model_list = stub.GetModelList(GetModelListRequest(use_filter=False))
    models = [m for m in model_list.models if m.state == Model.MODEL_STATE_LOADED]
    cache: Dict[str, Model] = {}
    for m in models:
        cache[m.uuid] = m
        cache[m.name.lower()] = m
    _MODEL_LIST = models
    _MODEL_CACHE = cache


def _get_models(stub: InferenceServiceStub) -> List[Model]:
    with _MODEL_LOCK:
        if not _MODEL_LIST:
            _load_models(stub)
        return list(_MODEL_LIST)


def _resolve_model(stub: InferenceServiceStub, model_str: Optional[str]) -> Tuple[Model, bool]:
    models = _get_models(stub)
    model_key = (model_str or "").strip()
    if model_key and model_key.lower() not in {"auto", "default"}:
        with _MODEL_LOCK:
            m = _MODEL_CACHE.get(model_key) or _MODEL_CACHE.get(model_key.lower())
        if m is not None:
            return m, bool(m.config.info.has_chain_of_thought)
    for m in models:
        if m.config.info.has_chain_of_thought:
            return m, True
    if not models:
        raise RuntimeError("No loaded models available")
    return models[0], bool(models[0].config.info.has_chain_of_thought)


def _flatten_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text") or "")
        return "".join(parts)
    return str(content)


def _build_tool_list(tools_spec: List[Dict[str, Any]]) -> List[Tool]:
    tools: List[Tool] = []
    for t in tools_spec:
        if t.get("type") != "function":
            continue
        fn = t.get("function", {})
        name = fn.get("name")
        if not name:
            continue
        tools.append(
            Tool(
                name=name,
                description=fn.get("description") or "",
                input_schema=fn.get("parameters") or {"type": "object"},
                display_name=name,
            )
        )
    return tools


def _tool_system_prompt(tools: List[Tool]) -> str:
    tool_desc = "\n".join([t.get_for_system_prompt() for t in tools])
    return (
        "You have access to the following tools:\n"
        f"{tool_desc}\n"
        f"When you decide to use a tool, respond with a JSON object enclosed by {TOOL_TAGS[0]} and {TOOL_TAGS[1]} tags in this format:\n"
        f"{TOOL_TAGS[0]}\n{{\n  \"tool\": \"<tool_name>\",\n  \"args\": {{<tool_arguments_as_json_object>}}\n}}\n{TOOL_TAGS[1]}\n"
        "Only use tools listed above, and ensure your JSON is valid."
    )


def _apply_tool_prompt(messages: List[Dict[str, Any]], prompt: str) -> None:
    for msg in messages:
        if msg.get("role") == "system":
            content = _flatten_content(msg.get("content"))
            msg["content"] = content + "\n\n" + prompt
            return
    messages.insert(0, {"role": "system", "content": prompt})


def _serialize_tool_calls(tool_calls: List[Dict[str, Any]]) -> str:
    chunks: List[str] = []
    for tc in tool_calls:
        if tc.get("type") != "function":
            continue
        fn = tc.get("function", {})
        name = fn.get("name")
        args_raw = fn.get("arguments")
        args: Any
        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {"_raw": args_raw}
        else:
            args = args_raw or {}
        payload = {"tool": name, "args": args}
        chunks.append(f"{TOOL_TAGS[0]}\n{json.dumps(payload)}\n{TOOL_TAGS[1]}")
    return "\n".join(chunks)


def _build_conversation(messages: List[Dict[str, Any]]) -> Conversation:
    convo = Conversation()
    tool_name_by_id: Dict[str, str] = {}
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []) or []:
                tc_id = tc.get("id")
                fn = (tc.get("function") or {})
                if tc_id and fn.get("name"):
                    tool_name_by_id[tc_id] = fn["name"]

    for msg in messages:
        role = msg.get("role")
        content = _flatten_content(msg.get("content"))
        if role == "assistant" and msg.get("tool_calls"):
            tool_blob = _serialize_tool_calls(msg.get("tool_calls") or [])
            content = (content + "\n" + tool_blob).strip()
        elif role == "tool":
            tool_name = msg.get("name") or tool_name_by_id.get(msg.get("tool_call_id"), "")
            content = f"<tool_result> \"tool\" : \"{tool_name}\" \"output\": \"{content}\" </tool_result>"

        if role == "system":
            convo.messages.add(role=Message.ROLE_SYSTEM, content=content)
        elif role == "user":
            convo.messages.add(role=Message.ROLE_USER, content=content)
        elif role == "assistant":
            convo.messages.add(role=Message.ROLE_ASSISTANT, content=content)
        elif role == "tool":
            convo.messages.add(role=Message.ROLE_TOOL, content=content)

    return convo


def _safe_parse_cot(raw: str) -> Tuple[str, str]:
    if THINK_TAGS[1] in raw:
        pre, post = raw.split(THINK_TAGS[1], 1)
        cot = pre.replace(THINK_TAGS[0], "").replace(THINK_TAGS[1], "").strip()
        return cot, post
    return "", raw


def _map_finish_reason(fr: Optional[int]) -> Optional[str]:
    if fr is None:
        return None
    if fr == FinishReason.FINISH_STOP:
        return "stop"
    if fr == FinishReason.FINISH_LENGTH:
        return "length"
    if fr == FinishReason.FINISH_TOOLCALLS:
        return "tool_calls"
    return "stop"


def _usage_to_openai(usage: Any) -> Dict[str, int]:
    tokens = getattr(usage, "tokens", None)
    if tokens is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt = int(getattr(tokens, "prompt", 0))
    completion = int(getattr(tokens, "completion", 0))
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


class _StreamFilter:
    def __init__(self, hide_cot: bool = False) -> None:
        self._buffer = ""
        self._mode = "normal"  # normal | think | toolcall
        self._max_tag = max(len("<think>"), len("</think>"), len("<toolcall>"), len("</toolcall>"))
        self._hide_cot = hide_cot
        self._passed_cot = not hide_cot
    def finalize(self) -> str:
        if self._mode != "normal":
            self._buffer = ""
            return ""
        tail = self._buffer
        self._buffer = ""
        return tail
    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        buf = self._buffer + chunk
        if not self._passed_cot:
            end = buf.find("</think>")
            if end == -1:
                # Keep only enough to detect a split closing tag.
                keep = len("</think>") - 1
                self._buffer = buf[-keep:] if keep > 0 else ""
                return ""
            buf = buf[end + len("</think>") :]
            self._passed_cot = True
        out_parts: List[str] = []
        while buf:
            if self._mode == "think":
                end = buf.find("</think>")
                if end == -1:
                    self._buffer = buf[-(self._max_tag - 1):]
                    return "".join(out_parts)
                buf = buf[end + len("</think>") :]
                self._mode = "normal"
                continue
            if self._mode == "toolcall":
                end = buf.find("</toolcall>")
                if end == -1:
                    self._buffer = buf[-(self._max_tag - 1):]
                    return "".join(out_parts)
                buf = buf[end + len("</toolcall>") :]
                self._mode = "normal"
                continue

            next_think = buf.find("<think>")
            next_tool = buf.find("<toolcall>")
            if next_think == -1 and next_tool == -1:
                if len(buf) >= self._max_tag:
                    out_parts.append(buf[: -(self._max_tag - 1)])
                    self._buffer = buf[-(self._max_tag - 1) :]
                else:
                    self._buffer = buf
                return "".join(out_parts)

            if next_think == -1 or (next_tool != -1 and next_tool < next_think):
                if next_tool > 0:
                    out_parts.append(buf[:next_tool])
                buf = buf[next_tool + len("<toolcall>") :]
                self._mode = "toolcall"
                continue

            if next_think > 0:
                out_parts.append(buf[:next_think])
            buf = buf[next_think + len("<think>") :]
            self._mode = "think"

        self._buffer = ""
        return "".join(out_parts)


class OpenAIProxy:
    def __init__(self, grpc_address: str, include_debug: bool = False) -> None:
        self.grpc_address = grpc_address
        self.include_debug = include_debug
        self.channel = grpc.insecure_channel(grpc_address)
        self.stub = InferenceServiceStub(self.channel)
        self.prompt_builder = AgentPromptBuilder()

    def build_request(self, payload: Dict[str, Any]) -> Tuple[IRequest, Model, bool, List[Tool], bool]:
        model_name = payload.get("model")
        model, is_reasoner = _resolve_model(self.stub, model_name)

        messages = list(payload.get("messages") or [])
        tools_spec = list(payload.get("tools") or [])
        tool_choice = payload.get("tool_choice")
        tool_choice_name = None
        if isinstance(tool_choice, dict):
            fn = tool_choice.get("function") or {}
            tool_choice_name = fn.get("name")
        allow_tools = tool_choice != "none"

        tools = _build_tool_list(tools_spec) if allow_tools else []
        if tool_choice_name:
            tools = [t for t in tools if t.name == tool_choice_name]

        if tools:
            _apply_tool_prompt(messages, _tool_system_prompt(tools))

        convo = _build_conversation(messages)
        convo.model_uuid = model.uuid

        req = IRequest()
        req.id = _gen_id("openai-proxy")
        req.model_uuid = model.uuid
        req.convo.CopyFrom(convo)

        if payload.get("max_tokens", 0) > 0:
            req.cfg.max_tokens = int(payload["max_tokens"])
        else:
            req.cfg.max_tokens = 16384 
        if payload.get("temperature") is not None:
            req.cfg.temp = float(payload["temperature"])
        if payload.get("top_p") is not None:
            req.cfg.top_p = float(payload["top_p"])

        response_format = payload.get("response_format") or {"type": "text"}
        rf_type = response_format.get("type") if isinstance(response_format, dict) else "text"

        if tools:
            if is_reasoner:
                _build_tool_call_response_format(req, tools)
            else:
                _build_tool_call_response_format_non_reasoning(req, tools)
        elif rf_type in {"json_schema", "json_object"}:
            if rf_type == "json_schema":
                schema = response_format.get("json_schema")
            else:
                schema = {"type": "object"}
            if is_reasoner:
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
                                "type": "tag",
                                "begin": "",
                                "content": {"type": "json_schema", "json_schema": schema},
                                "end": "",
                            },
                        ],
                    },
                }
                req.cfg.response_format.format = ResponseFormat.STRUCTURAL_TAG
                req.cfg.response_format.schema = json.dumps(structural_tag, indent=0)
            else:
                req.cfg.response_format.format = ResponseFormat.JSON
                req.cfg.response_format.schema = json.dumps(schema)

        stream = bool(payload.get("stream"))
        return req, model, is_reasoner, tools, stream

    def run_sync(self, req: IRequest) -> Any:
        return self.stub.GenerateSync(req)

    def run_stream(self, req: IRequest):
        return self.stub.Generate(req)


class OpenAIProxyHandler(BaseHTTPRequestHandler):
    server_version = "TruffleOpenAIProxy/0.1"
    def _set_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def _read_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _send_sse(self, payload: Dict[str, Any]) -> bool:
        data = json.dumps(payload)
        try:
            self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Client disconnected; stop streaming gracefully.
            self.close_connection = True
            return False
        return True

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if self.path in {"/v1/models", "/models"}:
            proxy: OpenAIProxy = self.server.proxy  # type: ignore[attr-defined]
            models = _get_models(proxy.stub)
            data = [
                {"id": m.uuid, "object": "model", "owned_by": m.provider or "truffle", "name": m.name}
                for m in models
            ]
            self._send_json(200, {"object": "list", "data": data})
            return
        if self.path.startswith("/v1/models/"):
            proxy: OpenAIProxy = self.server.proxy  # type: ignore[attr-defined]
            model_id = self.path.split("/v1/models/", 1)[1]
            models = _get_models(proxy.stub)
            model = next((m for m in models if m.uuid == model_id or m.name == model_id), None)
            if model is None:
                self._send_json(404, {"error": {"message": "model not found", "type": "not_found_error"}})
                return
            self._send_json(
                200,
                {
                    "id": model.uuid,
                    "object": "model",
                    "owned_by": model.provider or "truffle",
                    "name": model.name,
                },
            )
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_error(404, "Not Found")
            return
        try:
            payload = self._read_body()
        except Exception as e:
            self._send_json(400, {"error": {"message": str(e), "type": "invalid_request_error"}})
            return

        proxy: OpenAIProxy = self.server.proxy  # type: ignore[attr-defined]

        try:
            req, model, is_reasoner, _tools, stream = proxy.build_request(payload)
        except Exception as e:
            self._send_json(400, {"error": {"message": str(e), "type": "invalid_request_error"}})
            return

        if stream:
            self.send_response(200)
            self._set_cors_headers()
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            stream_id = _gen_id("chatcmpl")
            created = _now_ts()
            if not self._send_sse(
                {
                    "id": stream_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model.name,
                    "choices": [
                        {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
                    ],
                }
            ):
                return

            raw_content = ""
            last_finish = None
            filter_state = _StreamFilter(hide_cot=is_reasoner)

            for ir in proxy.run_stream(req):
                raw_content += ir.content
                if ir.HasField("finish_reason") and ir.finish_reason != FinishReason.FINISH_UNSPECIFIED:
                    last_finish = ir.finish_reason
                visible = filter_state.feed(ir.content)
                if visible:
                    if not self._send_sse(
                        {
                            "id": stream_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model.name,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": visible},
                                    "finish_reason": None,
                                }
                            ],
                        }
                    ):
                        return
            tail = filter_state.finalize()
            if tail:
                if not self._send_sse(
                    {
                        "id": stream_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model.name,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": tail},
                                "finish_reason": None,
                            }
                        ],
                    }
                ):
                    return
            _cot, after_cot = _safe_parse_cot(raw_content)
            tool_calls, _clean = proxy.prompt_builder.extract_tool_calls(after_cot)
            if tool_calls:
                tc_list = []
                for i, tc in enumerate(tool_calls):
                    name = tc.get("tool") or ""
                    args = json.dumps(tc.get("args") or {}, separators=(",", ":"))
                    tc_list.append(
                        {
                            "id": f"call_{i+1}",
                            "type": "function",
                            "function": {"name": name, "arguments": args},
                        }
                    )
                if not self._send_sse(
                    {
                        "id": stream_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model.name,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"tool_calls": tc_list},
                                "finish_reason": None,
                            }
                        ],
                    }
                ):
                    return
            finish_reason = _map_finish_reason(last_finish) or "stop"
            if not self._send_sse(
                {
                    "id": stream_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model.name,
                    "choices": [
                        {"index": 0, "delta": {}, "finish_reason": finish_reason}
                    ],
                }
            ):
                return
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                self.close_connection = True
            else:
                self.close_connection = True
            return

        resp = proxy.run_sync(req)
        raw = resp.content
        cot, after_cot = _safe_parse_cot(raw)
        tool_calls, clean = proxy.prompt_builder.extract_tool_calls(after_cot)
        message = clean_response(clean)

        finish_reason = _map_finish_reason(resp.finish_reason if resp.HasField("finish_reason") else None)
        openai_tool_calls = []
        for i, tc in enumerate(tool_calls):
            name = tc.get("tool") or ""
            args = json.dumps(tc.get("args") or {}, separators=(",", ":"))
            openai_tool_calls.append(
                {
                    "id": f"call_{i+1}",
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                }
            )

        msg: Dict[str, Any] = {"role": "assistant", "content": message}
        if openai_tool_calls:
            msg["tool_calls"] = openai_tool_calls
            if not message:
                msg["content"] = None

        response = {
            "id": _gen_id("chatcmpl"),
            "object": "chat.completion",
            "created": _now_ts(),
            "model": model.name,
            "choices": [
                {"index": 0, "message": msg, "finish_reason": finish_reason}
            ],
            "usage": _usage_to_openai(resp.usage if resp.HasField("usage") else None),
        }

        debug_req = bool(payload.get("debug") or payload.get("debug_reasoning"))
        if proxy.include_debug or debug_req:
            response["debug"] = {"reasoning": cot}

        self._send_json(200, response)

def normalize_grpc_address(address: str, default_port : int = 80) -> str:
    import socket 
    if '.local' in address:
        try:
            ip = socket.gethostbyname(address)
            address = ip
        except socket.gaierror as e:
            raise RuntimeError(f"Failed to resolve mDNS address {address}: {e}")
    if ':' not in address:
        address += f":{default_port}"
    return address

def main() -> None:
    parser = argparse.ArgumentParser(description="OpenAI-compatible proxy for Truffle gRPC inference")
    parser.add_argument("--truffle", default="truffle-1234", help="truffle id: e.g. truffle-1234")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    parser.add_argument("--debug", action="store_true", help="Include debug.reasoning in responses")
    args = parser.parse_args()
    print(f"Connecting to {args.truffle}")
    grpc_address = normalize_grpc_address(f"{args.truffle}.local", default_port=80)
    print(f"Found {args.truffle} at {grpc_address}")
    proxy = OpenAIProxy(grpc_address, include_debug=args.debug)

    class _Server(ThreadingHTTPServer):
        def __init__(self, server_address, handler_cls):
            super().__init__(server_address, handler_cls)
            self.proxy = proxy

    server = _Server((args.host, args.port), OpenAIProxyHandler)
    print(f"OpenAI proxy listening on http://{args.host}:{args.port} -> Truffle @ {grpc_address}")
    server.serve_forever()


if __name__ == "__main__":
    main()
