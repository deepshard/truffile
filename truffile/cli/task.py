from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import grpc
from google.protobuf.json_format import MessageToDict

from truffile.storage import StorageService
from truffile.transport.client import TruffleClient

from . import chat as chat_runtime
from .connect import _grpc_address, _resolve_connected_device
from .exit_codes import CONNECTION, ERROR, NOT_FOUND, SUCCESS, TIMEOUT, USAGE


def _emit_error(
    args: Any,
    message: str,
    *,
    code: str,
    device: str | None = None,
    task_id: str | None = None,
) -> None:
    chat_runtime._emit_oneshot_error(
        message,
        json_out=bool(getattr(args, "json", False)),
        code=code,
        device=device,
        task_id=task_id,
    )


def _state_from_task(task: Any) -> chat_runtime.TaskState:
    state = chat_runtime.TaskState()
    chat_runtime._apply_task_snapshot(task, state, quiet=True, emit_tools=False)
    return state


def _task_payload(task: Any, state: chat_runtime.TaskState, *, device: str) -> dict[str, Any]:
    payload = chat_runtime._state_payload(
        state,
        device=device,
        content=state.result_text,
        operation="inspect",
    )
    payload.update(
        {
            "node_count": len(task.nodes),
            "task_flags": task.task_flags,
            "app_uuids": list(task.info.app_uuids) if task.HasField("info") else [],
        }
    )
    return payload


def _task_events(task: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for node in task.nodes:
        created = node.created_at.ToDatetime().isoformat() if node.HasField("created_at") else None
        if node.HasField("user_msg"):
            events.append(
                {
                    "node_id": node.id,
                    "type": "user",
                    "created": created,
                    "content": node.user_msg.content,
                }
            )
        if not node.HasField("step"):
            continue
        step = node.step
        if step.HasField("thinking"):
            for summary in step.thinking.cot_summaries:
                events.append(
                    {
                        "node_id": node.id,
                        "type": "thinking",
                        "created": created,
                        "content": summary,
                    }
                )
        for tool_call in step.tool_calls:
            events.append(
                {
                    "node_id": node.id,
                    "type": "tool_call",
                    "created": created,
                    "tool": tool_call.tool_name,
                    "summary": tool_call.summary or None,
                    "arguments": tool_call.args or None,
                }
            )
        for tool_result in step.tool_results:
            events.append(
                {
                    "node_id": node.id,
                    "type": "tool_result",
                    "created": created,
                    "tool_call_id": tool_result.tool_call_id,
                    "is_error": tool_result.is_error,
                    "content": tool_result.content,
                }
            )
        if step.HasField("results"):
            content = step.results.content or step.results.summary
            if content:
                events.append(
                    {
                        "node_id": node.id,
                        "type": "result",
                        "created": created,
                        "content": content,
                    }
                )
        if step.HasField("user_response"):
            events.append(
                {
                    "node_id": node.id,
                    "type": "waiting_for_user",
                    "created": created,
                    "response_node_id": step.user_response.node_id,
                }
            )
    return events


async def _load_task(client: TruffleClient, task_id: str):
    task = await client.get_task(task_id, with_nodes=True)
    if not task.task_id:
        raise LookupError(f"task not found: {task_id}")
    return task


async def _dispatch_task(args: Any, client: TruffleClient, device: str) -> int:
    command = args.task_command

    if command == "list":
        limit = int(args.limit)
        if limit < 1:
            _emit_error(args, "--limit must be at least 1", code="usage_error", device=device)
            return USAGE
        tasks = await client.get_task_infos(max_before=limit)
        if args.json:
            print(json.dumps({"device": device, "tasks": tasks}, indent=2))
        else:
            for task in tasks:
                print(
                    f"{task['task_id']}\t{task.get('updated', '')[:19]}\t"
                    f"{task.get('title') or '(untitled)'}"
                )
        return SUCCESS

    task_id = args.task_id
    task = await _load_task(client, task_id)
    state = _state_from_task(task)

    if command in {"show", "status"}:
        payload = _task_payload(task, state, device=device)
        if command == "show" and getattr(args, "with_nodes", False):
            payload["raw_task"] = MessageToDict(
                task,
                preserving_proto_field_name=True,
            )
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"task_id:  {payload['task_id']}")
            print(f"title:    {payload['title'] or '(untitled)'}")
            print(f"status:   {payload['status']}")
            print(f"device:   {payload['device']}")
            print(f"created:  {payload['created'] or ''}")
            print(f"updated:  {payload['updated'] or ''}")
            print(f"nodes:    {payload['node_count']}")
            if payload["content"]:
                print("\n" + payload["content"])
        return SUCCESS

    if command == "logs":
        events = _task_events(task)
        if args.json:
            print(json.dumps({"device": device, "task_id": task_id, "events": events}, indent=2))
        else:
            for event in events:
                label = event["type"]
                content = event.get("content") or event.get("summary") or event.get("tool") or ""
                print(f"{event['node_id']}\t{label}\t{content}")
        return SUCCESS

    if command == "wait":
        if state.pending_node_id is None and state.run_state != "TASK_RUN_STATE_FATAL_ERROR":
            stream = client.open_existing_task_stream(task_id)
            await chat_runtime._stream_task(
                client,
                stream,
                state,
                quiet=True,
                emit_tools=not args.quiet,
                interrupt_on_cancel=False,
            )
        payload = _task_payload(task, state, device=device)
        payload["operation"] = "wait"
        payload["content"] = (
            "".join(chat_runtime._streaming_text).strip() or state.result_text
        ).strip()
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        elif payload["content"]:
            print(payload["content"])
        else:
            print(payload["status"])
        return SUCCESS

    if command == "interrupt":
        await client.interrupt_task(task_id)
        payload = {
            "device": device,
            "task_id": task_id,
            "status": "interrupt_requested",
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"interrupt requested for {task_id}")
        return SUCCESS

    if command == "rename":
        new_name = await client.rename_task(task_id, args.name)
        payload = {
            "device": device,
            "task_id": task_id,
            "status": "renamed",
            "name": new_name,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(new_name)
        return SUCCESS

    if command == "delete":
        if not args.yes:
            if args.json or not sys.stdin.isatty():
                _emit_error(
                    args,
                    "task delete requires --yes in noninteractive mode",
                    code="usage_error",
                    device=device,
                    task_id=task_id,
                )
                return USAGE
            answer = input(f"Delete task {task_id}? [y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("cancelled")
                return SUCCESS
        await client.delete_task(task_id)
        payload = {"device": device, "task_id": task_id, "status": "deleted"}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"deleted {task_id}")
        return SUCCESS

    _emit_error(args, f"unknown task command: {command}", code="usage_error", device=device)
    return USAGE


async def _run_task(args: Any, storage: StorageService) -> int:
    requested_device = getattr(args, "device", None)
    device, ip = await _resolve_connected_device(
        storage,
        requested_device,
        emit_errors=not bool(getattr(args, "json", False)),
    )
    if not device or not ip:
        _emit_error(
            args,
            f"could not resolve connected device{f' {requested_device}' if requested_device else ''}",
            code="connection_error",
            device=requested_device,
        )
        return CONNECTION
    token = storage.get_token(device)
    if not token:
        _emit_error(args, f"no token for {device}", code="connection_error", device=device)
        return CONNECTION

    client = TruffleClient(
        _grpc_address(ip),
        token=token,
        app_id=storage.app_id_for_device(device),
    )
    try:
        await client.connect()
        if not await client.check_auth():
            raise PermissionError("authentication failed")
        return await _dispatch_task(args, client, device)
    except grpc.aio.AioRpcError as exc:
        details = exc.details() or exc.code().name
        not_found = exc.code() == grpc.StatusCode.NOT_FOUND or "not found" in details.lower()
        _emit_error(
            args,
            details,
            code="not_found" if not_found else "execution_error",
            device=device,
            task_id=getattr(args, "task_id", None),
        )
        return NOT_FOUND if not_found else ERROR
    except LookupError as exc:
        _emit_error(
            args,
            str(exc),
            code="not_found",
            device=device,
            task_id=getattr(args, "task_id", None),
        )
        return NOT_FOUND
    except Exception as exc:
        _emit_error(
            args,
            str(exc),
            code="execution_error",
            device=device,
            task_id=getattr(args, "task_id", None),
        )
        return ERROR
    finally:
        await client.close()


async def cmd_task(args: Any, storage: StorageService) -> int:
    timeout = getattr(args, "timeout", None) if args.task_command == "wait" else None
    if timeout is not None and timeout <= 0:
        _emit_error(
            args,
            "--timeout must be greater than zero",
            code="usage_error",
            device=getattr(args, "device", None),
            task_id=getattr(args, "task_id", None),
        )
        return USAGE
    try:
        if timeout is None:
            return await _run_task(args, storage)
        async with asyncio.timeout(timeout):
            return await _run_task(args, storage)
    except TimeoutError:
        _emit_error(
            args,
            f"task wait timed out after {timeout:g} seconds",
            code="timeout",
            device=getattr(args, "device", None),
            task_id=getattr(args, "task_id", None),
        )
        return TIMEOUT
