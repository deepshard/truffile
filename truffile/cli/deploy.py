import asyncio
import os
import signal
import sys
from pathlib import Path

from truffile.storage import StorageService
from truffile.client import TruffleClient
from truffile.schema import validate_app_dir
from truffile.deploy import build_deploy_plan, deploy_with_builder

from .connect import _resolve_connected_device
from .ui import C, ARROW, CROSS, DOT, Spinner, ScrollingLog, error, warn, info, success


async def cmd_deploy(args, storage: StorageService) -> int:
    app_path = args.path if args.path else "."
    app_dir = Path(app_path).resolve()
    interactive = args.interactive
    dry_run = bool(getattr(args, "dry_run", False))
    if not app_dir.exists() or not app_dir.is_dir():
        error(f"{app_dir} is not a valid directory")
        return 1

    info(f"Validating app in {app_dir.name}")
    valid, config, app_type, warnings, errors = validate_app_dir(app_dir)
    if not valid or not app_type:
        for msg in errors:
            error(msg)
        return 1

    for w in warnings:
        warn(w)

    metadata = config.get("metadata", {}) if isinstance(config, dict) else {}
    icon_file = metadata.get("icon_file") if isinstance(metadata, dict) else None
    if not isinstance(icon_file, str) or not icon_file.strip():
        error("Deploy requires metadata.icon_file in truffile.yaml")
        return 1
    deploy_icon_path = app_dir / icon_file
    if not deploy_icon_path.exists() or not deploy_icon_path.is_file():
        error(f"Deploy requires an icon file; not found: {icon_file}")
        return 1
    if deploy_icon_path.stat().st_size == 0:
        error(f"Deploy requires a non-empty icon file: {icon_file}")
        return 1

    if dry_run:
        try:
            plan = build_deploy_plan(config=config, app_dir=app_dir, app_type=app_type)
        except Exception as e:
            error(f"Failed to build deploy plan: {e}")
            return 1
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
        print()
        success("Dry run complete (no device changes made)")
        return 0

    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return 1

    token = storage.get_token(device)
    if not token:
        error(f"No token for {device}")
        print(f"  {C.DIM}Run: truffile connect {device}{C.RESET}")
        return 1

    address = f"{ip}:80"
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
            )
        )
        return await deploy_task
    except asyncio.CancelledError:
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
        error(str(e))
        if client.app_uuid:
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
