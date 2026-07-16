import asyncio
import contextlib
import json
import os
import signal
import sys
from pathlib import Path

from truffile.storage import StorageService
from truffile.client import TruffleClient
from truffile.schema import validate_app_dir
from truffile.deploy import build_deploy_plan, deploy_with_builder

from .connect import _resolve_connected_device
from .output import emit_json, error_payload
from .ui import C, ARROW, CROSS, DOT, Spinner, ScrollingLog, error, warn, info, success


def _json_print(payload: dict) -> None:
    emit_json(payload)


@contextlib.contextmanager
def _suppress_deploy_progress():
    """Keep machine-mode stdout/stderr reserved for the final JSON payload."""
    with open(os.devnull, "w", encoding="utf-8") as sink:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            yield


def _deploy_error(json_out: bool, code: str, message: str, **extra) -> int:
    if json_out:
        payload = error_payload(code, message)
        payload["error"] = code  # compatibility with the initial deploy JSON contract
        payload.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})
        _json_print(payload)
    else:
        error(message)
    return 1


def _plan_json(plan: dict, app_dir: Path) -> dict:
    files = [
        {"source": f.get("source", ""), "destination": f.get("destination", "")}
        for f in plan["files_to_upload"]
    ]
    steps = [
        {
            "type": str(step.get("type", "") or ""),
            "name": str(step.get("name") or step.get("type") or "step"),
            "requires_input": str(step.get("type", "") or "") in {"text", "oauth"},
        }
        for step in plan["ordered_steps"]
    ]
    return {
        "name": plan["name"],
        "bundle_id": plan["bundle_id"],
        "mode": plan["finish_label"],
        "app_dir": str(app_dir),
        "files": files,
        "bash_steps": [name for name, _cmd in plan["bash_commands"]],
        "steps": steps,
        "input_requirements": _non_interactive_blockers(plan),
    }


def _non_interactive_blockers(plan: dict) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    for step in plan["ordered_steps"]:
        step_type = str(step.get("type", "") or "")
        if step_type in {"text", "oauth"}:
            blockers.append({
                "type": step_type,
                "name": str(step.get("name") or step_type),
            })
    return blockers


async def _replace_existing_app(
    *,
    address: str,
    token: str,
    storage: StorageService,
    device: str,
    bundle_id: str,
    json_out: bool,
) -> tuple[int, dict | None]:
    client = TruffleClient(address, token=token, app_id=storage.app_id_for_device(device))
    spinner = None if json_out else Spinner("Checking for existing app")
    if spinner:
        spinner.start()
    try:
        await client.connect()
        apps = await client.get_all_apps()
        matches = [
            app for app in apps
            if getattr(app.metadata, "bundle_id", "") == bundle_id
        ]
        if spinner:
            spinner.stop(success=True)
        if not matches:
            return 0, None
        if len(matches) > 1:
            names = ", ".join(f"{app.metadata.name} ({app.uuid})" for app in matches)
            return _deploy_error(
                json_out,
                "replace_ambiguous",
                f"Multiple installed apps match bundle id {bundle_id}: {names}",
            ), None

        app = matches[0]
        delete_spinner = None if json_out else Spinner(f"Replacing existing {app.metadata.name}")
        if delete_spinner:
            delete_spinner.start()
        await client.delete_app(app.uuid)
        if delete_spinner:
            delete_spinner.stop(success=True)
        return 0, {"name": app.metadata.name, "uuid": app.uuid}
    except Exception as exc:
        if spinner:
            spinner.fail(str(exc))
        return _deploy_error(json_out, "replace_failed", str(exc)), None
    finally:
        await client.close()


async def cmd_deploy(args, storage: StorageService) -> int:
    app_path = args.path if args.path else "."
    if app_path == "obsidian":
        from .obsidian import cmd_obsidian_deploy

        return await cmd_obsidian_deploy(args, storage)

    app_dir = Path(app_path).resolve()
    interactive = args.interactive
    dry_run = bool(getattr(args, "dry_run", False))
    json_out = bool(getattr(args, "json", False))
    non_interactive = bool(getattr(args, "non_interactive", False))
    replace = bool(getattr(args, "replace", False))
    if interactive and non_interactive:
        return _deploy_error(json_out, "invalid_args", "--interactive and --non-interactive cannot be used together")
    if not app_dir.exists() or not app_dir.is_dir():
        return _deploy_error(json_out, "invalid_path", f"{app_dir} is not a valid directory")

    if not json_out:
        info(f"Validating app in {app_dir.name}")
    valid, config, app_type, warnings, errors = validate_app_dir(app_dir)
    if not valid or not app_type:
        if json_out:
            return _deploy_error(json_out, "validation_failed", "App validation failed", errors=errors)
        for msg in errors:
            error(msg)
        return 1

    for w in warnings:
        if not json_out:
            warn(w)

    metadata = config.get("metadata", {}) if isinstance(config, dict) else {}
    icon_file = metadata.get("icon_file") if isinstance(metadata, dict) else None
    if not isinstance(icon_file, str) or not icon_file.strip():
        return _deploy_error(json_out, "missing_icon", "Deploy requires metadata.icon_file in truffile.yaml")
    deploy_icon_path = app_dir / icon_file
    if not deploy_icon_path.exists() or not deploy_icon_path.is_file():
        return _deploy_error(json_out, "missing_icon", f"Deploy requires an icon file; not found: {icon_file}")
    if deploy_icon_path.stat().st_size == 0:
        return _deploy_error(json_out, "empty_icon", f"Deploy requires a non-empty icon file: {icon_file}")

    try:
        plan = build_deploy_plan(config=config, app_dir=app_dir, app_type=app_type)
    except Exception as e:
        return _deploy_error(json_out, "plan_failed", f"Failed to build deploy plan: {e}")

    if dry_run:
        if json_out:
            _json_print({
                "status": "ok",
                "dry_run": True,
                "app": _plan_json(plan, app_dir),
                "warnings": warnings,
            })
            return 0
        print()
        print(f"{C.BOLD}Dry Run: Deploy Plan{C.RESET}")
        print(f"  Name: {plan['name']}")
        print(f"  Bundle ID: {plan['bundle_id']}")
        print(f"  Mode: {plan['finish_label']}")
        print(f"  App Dir: {app_dir}")
        print(f"  Exec CWD: {plan['exec_cwd']}")
        if plan["icon_path"] is not None:
            print(f"  Icon: {plan['icon_path']}")
        else:
            print(f"  Icon: {C.DIM}<none>{C.RESET}")

        fg = plan["fg_payload"]
        if fg is not None:
            fg_keys = [e.split("=", 1)[0] for e in fg.get("env", []) if "=" in e]
            print(f"  Foreground Cmd: {fg['cmd']} {' '.join(fg.get('args', []))}".rstrip())
            print(f"  Foreground Env Keys: {', '.join(fg_keys) if fg_keys else '<none>'}")

        bg = plan["bg_payload"]
        if bg is not None:
            bg_keys = [e.split('=', 1)[0] for e in bg.get("env", []) if "=" in e]
            print(f"  Background Cmd: {bg['cmd']} {' '.join(bg.get('args', []))}".rstrip())
            print(f"  Background Env Keys: {', '.join(bg_keys) if bg_keys else '<none>'}")
            if plan["default_schedule"] is not None:
                print(f"  Background Schedule: configured")
            else:
                print(f"  Background Schedule: {C.DIM}<default runtime policy>{C.RESET}")

        files = plan["files_to_upload"]
        print(f"  Files To Upload: {len(files)}")
        for f in files:
            src = f.get("source", "<missing>")
            dst = f.get("destination", "<missing>")
            print(f"    - {src} {ARROW} {dst}")

        cmds = plan["bash_commands"]
        print(f"  Bash Steps: {len(cmds)}")
        for name, _cmd in cmds:
            print(f"    - {name}")
        print(f"  Ordered Steps: {len(plan['ordered_steps'])}")
        for index, step in enumerate(plan["ordered_steps"], start=1):
            step_type = str(step.get("type", "") or "")
            step_name = str(step.get("name") or step_type or "step")
            boundary = " (interactive input required)" if step_type in {"text", "oauth"} else ""
            print(f"    {index}. {step_name} [{step_type}]{boundary}")
        print()
        success("Dry run complete (no device changes made)")
        return 0

    if non_interactive:
        blockers = _non_interactive_blockers(plan)
        if blockers:
            return _deploy_error(
                json_out,
                "input_required",
                "Deploy requires interactive input for one or more steps",
                steps=blockers,
            )

    device, ip = await _resolve_connected_device(storage, quiet=json_out)
    if not device or not ip:
        if json_out:
            return _deploy_error(
                json_out,
                "device_unreachable",
                "The connected Truffle device could not be resolved",
                retryable=True,
                next_action="Run truffile scan --json, then reconnect if needed",
            )
        return 1

    token = storage.get_token(device)
    if not token:
        if json_out:
            return _deploy_error(json_out, "missing_token", f"No token for {device}")
        error(f"No token for {device}")
        print(f"  {C.DIM}Run: truffile connect {device}{C.RESET}")
        return 1

    address = f"{ip}:80"
    replaced_app = None
    if replace:
        replace_code, replaced_app = await _replace_existing_app(
            address=address,
            token=token,
            storage=storage,
            device=device,
            bundle_id=plan["bundle_id"],
            json_out=json_out,
        )
        if replace_code != 0:
            return replace_code

    client = TruffleClient(address, token=token, app_id=storage.app_id_for_device(device))
    deploy_task = None

    loop = asyncio.get_event_loop()

    def handle_sigint():
        print("\nInterrupted!")
        if deploy_task and not deploy_task.done():
            deploy_task.cancel()

    loop.add_signal_handler(signal.SIGINT, handle_sigint)

    try:
        deploy_task = asyncio.create_task(
            deploy_with_builder(
                client=client,
                config=config,
                app_dir=app_dir,
                app_type=app_type,
                device=device,
                interactive=interactive,
                spinner_cls=Spinner,
                scrolling_log_cls=ScrollingLog,
                info=info,
                success=success,
                error=error,
                color_dim=C.DIM,
                color_reset=C.RESET,
                color_bold=C.BOLD,
                arrow=ARROW,
                interactive_shell=_interactive_shell,
                non_interactive=non_interactive,
            )
        )
        if json_out:
            with _suppress_deploy_progress():
                result = await deploy_task
        else:
            result = await deploy_task
        if result == 0 and json_out:
            _json_print({
                "status": "ok",
                "app": {
                    "name": plan["name"],
                    "bundle_id": plan["bundle_id"],
                    "mode": plan["finish_label"],
                },
                "build_session": client.last_app_uuid,
                "replaced": replaced_app,
                "warnings": warnings,
            })
        return result
    except asyncio.CancelledError:
        if json_out:
            with _suppress_deploy_progress():
                print()
                spinner = Spinner("Discarding build session")
                spinner.start()
                if client.app_uuid:
                    try:
                        await client.discard()
                        spinner.stop(success=True)
                    except Exception:
                        spinner.fail("Failed to discard")
            _deploy_error(json_out, "interrupted", "Deploy interrupted")
        else:
            print()
            spinner = Spinner("Discarding build session")
            spinner.start()
            if client.app_uuid:
                try:
                    await client.discard()
                    spinner.stop(success=True)
                except Exception:
                    spinner.fail("Failed to discard")
        return 130
    except Exception as e:
        if json_out:
            _deploy_error(json_out, "deploy_failed", str(e))
        else:
            error(str(e))
        if client.app_uuid:
            if json_out:
                with _suppress_deploy_progress():
                    spinner = Spinner("Discarding build session")
                    spinner.start()
                    try:
                        await client.discard()
                        spinner.stop(success=True)
                    except Exception:
                        spinner.fail("Failed to discard")
            else:
                spinner = Spinner("Discarding build session")
                spinner.start()
                try:
                    await client.discard()
                    spinner.stop(success=True)
                except Exception:
                    spinner.fail("Failed to discard")
        return 1
    finally:
        loop.remove_signal_handler(signal.SIGINT)
        await client.close()


async def _interactive_shell(ws_url: str) -> int:
        print(f"{C.DIM}Opening shell... (exit with Ctrl+D or 'exit'){C.RESET}")
        import os, termios, fcntl, struct, tty, contextlib, json
        try:
            import websockets
            from websockets.exceptions import ConnectionClosed, ConnectionClosedOK
        except Exception:
            print(f"{C.RED}{CROSS} Error:{C.RESET} websockets package is required for terminal mode")
            return 67

        def _winsz():
            try:
                h, w, _, _ = struct.unpack("HHHH", fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0"*8))
                return w, h
            except Exception:
                return 80, 24

        class Raw:
            def __enter__(self):
                self.fd = sys.stdin.fileno()
                self.old = termios.tcgetattr(self.fd)
                tty.setraw(self.fd); return self
            def __exit__(self, *a):
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)

        async def run_once():
            async with websockets.connect(ws_url, max_size=None, ping_interval=30) as ws:
                cols, rows = _winsz()
                await ws.send(json.dumps({"resize":[cols, rows]}))

                loop = asyncio.get_running_loop()
                q: asyncio.Queue[bytes] = asyncio.Queue()
                stop = asyncio.Event()

                def on_stdin():
                    try:
                        data = os.read(sys.stdin.fileno(), 4096)
                        if data: q.put_nowait(data)
                    except BlockingIOError:
                        pass
                loop.add_reader(sys.stdin.fileno(), on_stdin)

                async def pump_in():
                    try:
                        while not stop.is_set():
                            data = await q.get()
                            try: await ws.send(data)
                            except (ConnectionClosed, ConnectionClosedOK): break
                    finally:
                        stop.set()
                async def pump_out():
                    try:
                        async for msg in ws:
                            if isinstance(msg, bytes):
                                os.write(sys.stdout.fileno(), msg)
                            else:
                                os.write(sys.stdout.fileno(), msg.encode()) # type: ignore
                    except (ConnectionClosed, ConnectionClosedOK):
                        pass
                    finally:
                        stop.set()

                with Raw():
                    t_in = asyncio.create_task(pump_in())
                    t_out = asyncio.create_task(pump_out())
                    try:
                        await asyncio.wait({t_in, t_out}, return_when=asyncio.FIRST_COMPLETED)
                    finally:
                        stop.set(); t_in.cancel(); t_out.cancel()
                        with contextlib.suppress(Exception):
                            await asyncio.gather(t_in, t_out, return_exceptions=True)
                        loop.remove_reader(sys.stdin.fileno())


        await run_once()
        return 67
