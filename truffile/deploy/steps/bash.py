from __future__ import annotations

import json
from typing import Any, Callable

from truffile.transport.client import TruffleClient

from .env import build_env_prefix


async def handle_bash(
    step: dict[str, Any],
    *,
    client: TruffleClient,
    exec_cwd: str,
    info: Callable,
    error: Callable,
    scrolling_log_cls: Any,
    collected_env: dict[str, str] | None = None,
    **_kw: Any,
) -> None:
    step_name = step.get("name", "bash")
    run_cmd = f"{build_env_prefix(collected_env)}{step['run']}"
    info(f"Running: {step_name}")
    log = scrolling_log_cls(height=6, prefix="  ")
    exit_code = 0
    async for ev, data in client.exec_stream(run_cmd, cwd=exec_cwd):
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
        error(f"Step '{step_name}' failed with exit code {exit_code}")
        raise RuntimeError(f"Step '{step_name}' failed with exit code {exit_code}")
