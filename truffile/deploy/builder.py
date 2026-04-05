from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from truffile.transport.client import TruffleClient
from .plan import build_deploy_plan, _env_map_to_list
from .steps import handle_bash, handle_files, handle_text

STEP_HANDLERS = {
    "bash": handle_bash,
    "files": handle_files,
    "text": handle_text,
}


async def _wait_for_build_session_ready(client: TruffleClient, timeout_sec: float = 45.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last_error: Exception | None = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            result = await client.exec("echo ready", cwd="/")
            if result.exit_code == 0:
                return
        except Exception as e:
            last_error = e
        await asyncio.sleep(1.0)
    msg = f"build session did not become ready in time"
    if last_error:
        msg += f": {last_error}"
    raise RuntimeError(msg)


async def deploy_with_builder(
    *,
    client: TruffleClient,
    config: dict[str, Any],
    app_dir: Path,
    app_type: str,
    device: str,
    interactive: bool,
    spinner_cls: Any,
    scrolling_log_cls: Any,
    info: Callable[[str], None],
    success: Callable[[str], None],
    error: Callable[[str], None],
    color_dim: str,
    color_reset: str,
    color_bold: str,
    arrow: str,
    interactive_shell: Callable[[str], Any],
) -> int:
    plan = build_deploy_plan(config=config, app_dir=app_dir, app_type=app_type)

    spinner = spinner_cls(f"Connecting to {device}")
    spinner.start()
    await client.connect()
    spinner.stop(success=True)

    spinner = spinner_cls("Starting build session")
    spinner.start()
    await client.start_build()
    await _wait_for_build_session_ready(client)
    spinner.stop(success=True)
    print(f"  {color_dim}Session: {client.app_uuid}{color_reset}")

    collected_env: dict[str, str] = {}

    ctx = dict(
        client=client,
        app_dir=app_dir,
        exec_cwd=plan["exec_cwd"],
        spinner_cls=spinner_cls,
        scrolling_log_cls=scrolling_log_cls,
        info=info,
        success=success,
        error=error,
        color_dim=color_dim,
        color_reset=color_reset,
        color_bold=color_bold,
        arrow=arrow,
        collected_env=collected_env,
    )

    for step in plan["ordered_steps"]:
        step_type = step.get("type", "")
        handler = STEP_HANDLERS.get(step_type)
        if handler:
            await handler(step, **ctx)

    # inject collected env vars into process configs
    fg_payload = plan["fg_payload"]
    bg_payload = plan["bg_payload"]
    if collected_env:
        env_list = _env_map_to_list(collected_env)
        if fg_payload:
            fg_payload["env"] = fg_payload.get("env", []) + env_list
        if bg_payload:
            bg_payload["env"] = bg_payload.get("env", []) + env_list

    if interactive:
        print()
        info("Opening interactive shell (exit with Ctrl+D or 'exit' to finish deploy)")
        ws_url = str(client.http_base or "").replace("http://", "ws://").replace("https://", "wss://") + "/term"
        await interactive_shell(ws_url)
        print()

    spinner = spinner_cls(f"Finishing as {plan['finish_label']} app")
    spinner.start()

    await client.finish_app(
        name=plan["name"],
        bundle_id=plan["bundle_id"],
        description=plan["description"],
        icon=plan["icon_path"],
        foreground=fg_payload,
        background=bg_payload,
        default_schedule=plan["default_schedule"],
    )

    spinner.stop(success=True)
    print()
    success(f"Deployed: {color_bold}{plan['name']}{color_reset} ({plan['finish_label']})")
    return 0
