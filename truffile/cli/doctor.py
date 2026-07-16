from __future__ import annotations

import asyncio
from importlib import resources
from pathlib import Path
from typing import Any, Awaitable

import httpx

from truffile import __version__
from truffile.client import TruffleClient, resolve_mdns
from truffile.storage import StorageService

from .in_container import in_container_http_headers
from .output import emit_json, error_payload, exception_details, ok_payload
from .ui import C, CHECK, CROSS


def _ok(message: str, **details: Any) -> dict[str, Any]:
    return {"status": "ok", "message": message, **details}


def _failed(message: str, **details: Any) -> dict[str, Any]:
    return {"status": "error", "message": message, **details}


def _skipped(message: str, **details: Any) -> dict[str, Any]:
    return {"status": "skipped", "message": message, **details}


async def _bounded(awaitable: Awaitable[Any], timeout: float) -> Any:
    return await asyncio.wait_for(awaitable, timeout=timeout)


def _resource_check() -> dict[str, Any]:
    bundled_skills = resources.files("truffile").joinpath("skills")
    bundled_examples = resources.files("truffile").joinpath("app-store")
    workspace_root = Path.cwd() / "truffile"
    bundled = {
        "skills": bundled_skills.is_dir(),
        "examples": bundled_examples.is_dir(),
    }
    workspace = {
        "skills": {
            "path": str(workspace_root / "skills"),
            "present": (workspace_root / "skills").is_dir(),
        },
        "examples": {
            "path": str(workspace_root / "examples"),
            "present": (workspace_root / "examples").is_dir(),
        },
    }
    missing = [name for name, present in bundled.items() if not present]
    if missing:
        return _failed(
            f"Bundled resources are missing: {', '.join(missing)}",
            code="bundled_resources_missing",
            retryable=False,
            next_action="Reinstall or upgrade Truffile",
            missing=missing,
            bundled=bundled,
            workspace=workspace,
        )
    return _ok(
        "Bundled resources are present",
        cli_version=__version__,
        bundled=bundled,
        workspace=workspace,
    )


async def _if2_check(ip: str, timeout: float) -> dict[str, Any]:
    url = f"http://{ip}/if2/v1/models"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=in_container_http_headers())
            response.raise_for_status()
            payload = response.json()
        models = payload.get("data", [])
        if not isinstance(models, list):
            return _failed("IF2 returned an invalid models payload", service="if2", url=url)
        return _ok("IF2 is available", service="if2", url=url, model_count=len(models))
    except Exception as exc:
        details = exception_details(exc, default_code="if2_unavailable")
        return _failed(
            details.pop("message"),
            service="if2",
            url=url,
            **details,
        )


async def cmd_doctor(args, storage: StorageService) -> int:
    json_out = bool(getattr(args, "json", False))
    timeout = max(0.1, float(getattr(args, "timeout", 15.0) or 15.0))
    check_builder = bool(getattr(args, "builder", False))
    in_container = getattr(storage, "_in_container_info", None)

    checks: dict[str, dict[str, Any]] = {
        "package": _ok(f"Truffile {__version__} is installed", version=__version__),
        "resources": _resource_check(),
        "execution_context": _ok(
            "Running inside a Truffle app container" if in_container else "Running on this computer",
            mode="truffle_container" if in_container else "computer",
            grpc_address=getattr(in_container, "grpc_address", None),
        ),
    }

    device = storage.state.last_used_device
    if not device:
        checks["discovery"] = _skipped("No saved device to resolve")
        checks["saved_session"] = _failed(
            "No Truffle device is connected",
            code="device_required",
            next_action="Onboard in Symphony, then run truffile connect <device> --user-id <user-id>",
        )
        checks["task_convo"] = _skipped("Requires a connected device")
        checks["if2"] = _skipped("Requires a connected device")
        checks["app_runtime"] = _skipped("Requires a connected device")
        checks["builder"] = _skipped("Requires a connected device")
        return _finish(checks, json_out=json_out)

    if in_container is not None:
        ip = in_container.host
        checks["discovery"] = _ok(
            "Using the runtime-provided host address",
            device=device,
            address=in_container.grpc_address,
            method="runtime",
        )
    else:
        try:
            ip = await _bounded(resolve_mdns(f"{device}.local"), timeout)
            checks["discovery"] = _ok(
                f"Resolved {device}.local",
                device=device,
                ip=ip,
                method="mdns",
            )
        except Exception as exc:
            checks["discovery"] = _failed(
                f"Could not resolve {device}.local: {exc}",
                code="device_unreachable",
                device=device,
                retryable=True,
            )
            checks["saved_session"] = _skipped("Device discovery failed")
            checks["task_convo"] = _skipped("Device discovery failed")
            checks["if2"] = _skipped("Device discovery failed")
            checks["app_runtime"] = _skipped("Device discovery failed")
            checks["builder"] = _skipped("Device discovery failed")
            return _finish(checks, json_out=json_out)

    token = storage.get_token(device)
    if not token:
        checks["saved_session"] = _failed(
            f"No saved session token for {device}",
            code="missing_token",
            next_action=f"Run truffile connect {device} --user-id <user-id>",
        )
        checks["task_convo"] = _skipped("Requires an authenticated session")
        checks["if2"] = await _if2_check(ip, timeout)
        checks["app_runtime"] = _skipped("Requires an authenticated session")
        checks["builder"] = _skipped("Requires an authenticated session")
        return _finish(checks, json_out=json_out)

    client = TruffleClient(
        f"{ip}:80",
        token=token,
        app_id=storage.app_id_for_device(device),
    )
    try:
        try:
            await client.connect(timeout=timeout)
            authenticated = await _bounded(client.check_auth(), timeout)
            if not authenticated:
                checks["saved_session"] = _failed(
                    "The saved session token was rejected",
                    code="authentication_failed",
                    next_action=f"Run truffile connect {device} --user-id <user-id>",
                )
            else:
                checks["saved_session"] = _ok("The saved session is valid", device=device)
        except Exception as exc:
            details = exception_details(exc, default_code="grpc_unavailable")
            checks["saved_session"] = _failed(
                details.pop("message"),
                device=device,
                **details,
            )
            authenticated = False

        if authenticated:
            try:
                tasks = await _bounded(client.get_task_infos(max_before=1), timeout)
                checks["task_convo"] = _ok(
                    "Task/Convo is available",
                    service="task_convo",
                    recent_task_count=len(tasks),
                )
            except Exception as exc:
                checks["task_convo"] = _failed(
                    str(exc),
                    code="task_convo_unavailable",
                    service="task_convo",
                )

            try:
                apps = await _bounded(client.get_all_apps(), timeout)
                checks["app_runtime"] = _ok(
                    "App runtime is available",
                    service="app_runtime",
                    installed_app_count=len(apps),
                )
            except Exception as exc:
                checks["app_runtime"] = _failed(
                    str(exc),
                    code="app_runtime_unavailable",
                    service="app_runtime",
                )

            if check_builder:
                try:
                    await _bounded(client.start_build(), timeout)
                    await _bounded(client.discard(), timeout)
                    checks["builder"] = _ok(
                        "Builder opened and discarded a disposable build session",
                        service="builder",
                    )
                except Exception as exc:
                    if client.app_uuid:
                        try:
                            await _bounded(client.discard(), timeout)
                        except Exception:
                            pass
                    checks["builder"] = _failed(
                        str(exc),
                        code="builder_unavailable",
                        service="builder",
                    )
            else:
                checks["builder"] = _skipped(
                    "Builder probe is opt-in because it opens and discards a build session",
                    next_action="Run truffile doctor --builder --json",
                )
        else:
            checks["task_convo"] = _skipped("Requires an authenticated session")
            checks["app_runtime"] = _skipped("Requires an authenticated session")
            checks["builder"] = _skipped("Requires an authenticated session")

        checks["if2"] = await _if2_check(ip, timeout)
    finally:
        await client.close()

    return _finish(checks, json_out=json_out)


def _finish(checks: dict[str, dict[str, Any]], *, json_out: bool) -> int:
    failed = [name for name, check in checks.items() if check.get("status") == "error"]
    healthy = not failed
    if json_out:
        if healthy:
            emit_json(ok_payload(healthy=True, checks=checks))
        else:
            emit_json(error_payload(
                "health_checks_failed",
                f"{len(failed)} health check(s) failed",
                retryable=any(bool(checks[name].get("retryable")) for name in failed),
                healthy=False,
                failed_checks=failed,
                checks=checks,
            ))
    else:
        print(f"{C.BOLD}Truffile doctor{C.RESET}")
        for name, check in checks.items():
            status = check.get("status")
            if status == "ok":
                icon = f"{C.GREEN}{CHECK}{C.RESET}"
            elif status == "error":
                icon = f"{C.RED}{CROSS}{C.RESET}"
            else:
                icon = f"{C.DIM}-{C.RESET}"
            print(f"  {icon} {name}: {check.get('message', '')}")
    return 0 if healthy else 1
