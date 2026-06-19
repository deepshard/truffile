from __future__ import annotations

import getpass
import json
from typing import Any, Callable

from truffile.transport.client import TruffleClient

from .env import build_env_prefix


async def handle_text(
    step: dict[str, Any],
    *,
    client: TruffleClient,
    exec_cwd: str,
    info: Callable,
    error: Callable,
    scrolling_log_cls: Any,
    collected_env: dict[str, str],
    **_kw: Any,
) -> None:
    step_name = step.get("name", "Configure")
    content = step.get("content", "")
    if content:
        print()
        info(step_name)
        print(content.strip())

    for field in step.get("fields", []):
        label = field.get("label", field.get("name", ""))
        field_type = field.get("type", "text")
        placeholder = field.get("placeholder", "")
        default = field.get("default", "")
        prompt = f"  {label}"
        if placeholder:
            prompt += f" ({placeholder})"
        prompt += ": "

        if field_type == "password":
            value = getpass.getpass(prompt)
        else:
            value = input(prompt)

        if not value.strip() and default:
            value = default
        if not value.strip() and field.get("env_default_if_empty"):
            value = field["env_default_if_empty"]

        env_key = field.get("env")
        if env_key:
            collected_env[env_key] = value

    # run validator if present — prepend env vars to the command
    # since each exec call is a fresh shell
    validator = step.get("validator")
    if not validator:
        return

    validator_cmd = validator.get("run", "")
    if not validator_cmd:
        return

    env_prefix = build_env_prefix(collected_env)
    full_cmd = f"{env_prefix}{validator_cmd}"

    info("Validating...")
    log = scrolling_log_cls(height=4, prefix="  ")
    exit_code = 0
    async for ev, data in client.exec_stream(full_cmd, cwd=exec_cwd):
        if ev == "log":
            try:
                line = json.loads(data).get("line", "")
            except Exception:
                line = data
            log.add(line)
        elif ev == "exit":
            try:
                exit_code = int(json.loads(data).get("code", 0))
            except (ValueError, KeyError):
                pass
    log.finish()

    if exit_code != 0:
        error_msg = validator.get("error_message", "Validation failed. Check your input.")
        error(error_msg.strip())
        raise RuntimeError(f"Validator failed for step '{step_name}'")
