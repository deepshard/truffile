import argparse
import asyncio
import json
import signal
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from truffile.storage import StorageService
from truffile.client import TruffleClient, resolve_mdns, NewSessionStatus
from truffile.schema import validate_app_dir
from truffile.deploy import build_deploy_plan, deploy_with_builder


# ANSI colors
class C:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# Icons
MUSHROOM = "🍄‍🟫"
CHECK = "✓"
CROSS = "✗"
ARROW = "→"
DOT = "•"
WARN = "⚠"


class Spinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    
    def __init__(self, message: str):
        self.message = message
        self.running = False
        self.thread = None
        self.frame_idx = 0
    
    def _spin(self):
        while self.running:
            frame = self.FRAMES[self.frame_idx % len(self.FRAMES)]
            sys.stdout.write(f"\r{C.CYAN}{frame}{C.RESET} {self.message}")
            sys.stdout.flush()
            self.frame_idx += 1
            time.sleep(0.08)
    
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()
    
    def stop(self, success: bool = True):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        icon = f"{C.GREEN}{CHECK}{C.RESET}" if success else f"{C.RED}{CROSS}{C.RESET}"
        sys.stdout.write(f"\r{icon} {self.message}\n")
        sys.stdout.flush()
    
    def fail(self, message: str | None = None):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        msg = message or self.message
        sys.stdout.write(f"\r{C.RED}{CROSS}{C.RESET} {msg}\n")
        sys.stdout.flush()


class ScrollingLog:
    #felt a little fancy lol
    """A scrolling log window that shows the last N lines in place."""
    
    def __init__(self, height: int = 6, prefix: str = "  "):
        self.height = height
        self.prefix = prefix
        self.lines: list[str] = []
        self.started = False
        try:
            import shutil
            self.width = shutil.get_terminal_size().columns - len(prefix) - 2
        except Exception:
            self.width = 76
    
    def _truncate(self, line: str) -> str:
        if len(line) > self.width:
            return line[:self.width - 3] + "..."
        return line
    
    def _render(self):
        if self.started:
            sys.stdout.write(f"\033[{self.height}A")
        
        display = self.lines[-self.height:] if len(self.lines) >= self.height else self.lines
        
        while len(display) < self.height:
            display.insert(0, "")
        
        for line in display:
            truncated = self._truncate(line)
            sys.stdout.write(f"\033[K{self.prefix}{C.DIM}{truncated}{C.RESET}\n")
        
        sys.stdout.flush()
        self.started = True
    
    def add(self, line: str):
        self.lines.append(line.rstrip())
        self._render()
    
    def finish(self):
        if self.started:
            sys.stdout.write(f"\033[{self.height}A")
            for _ in range(self.height):
                sys.stdout.write("\033[K\n")
            sys.stdout.write(f"\033[{self.height}A")
            sys.stdout.flush()


def error(msg: str):
    print(f"{C.RED}{CROSS} Error:{C.RESET} {msg}")


def warn(msg: str):
    print(f"{C.YELLOW}{WARN} Warning:{C.RESET} {msg}")


def success(msg: str):
    print(f"{C.GREEN}{CHECK}{C.RESET} {msg}")


def info(msg: str):
    print(f"{C.CYAN}{DOT}{C.RESET} {msg}")


async def cmd_connect(args, storage: StorageService) -> int:
    device_name = args.device
    
    spinner = Spinner(f"Resolving {device_name}.local")
    spinner.start()
    
    hostname = f"{device_name}.local"
    try:
        ip = await resolve_mdns(hostname)
        spinner.stop(success=True)
    except RuntimeError:
        spinner.fail(f"Could not resolve {device_name}.local")
        print()
        print(f"  {C.DIM}Try running:{C.RESET}")
        print(f"    {C.CYAN}ping {device_name}.local{C.RESET}")
        print()
        print(f"  {C.DIM}If ping fails, check:{C.RESET}")
        print(f"  {C.DIM}{DOT} Device is powered on and connected to WiFi{C.RESET}")
        print(f"  {C.DIM}{DOT} Your computer is on the same network{C.RESET}")
        print(f"  {C.DIM}{DOT} mDNS is working{C.RESET}")
        print()
        return 1
    
    address = f"{ip}:80"
    existing_token = storage.get_token(device_name)
    
    if existing_token:
        spinner = Spinner("Validating existing token")
        spinner.start()
        client = TruffleClient(address, existing_token)
        try:
            await client.connect()
            if await client.check_auth():
                spinner.stop(success=True)
                storage.set_last_used(device_name)
                success(f"Already connected to {C.BOLD}{device_name}{C.RESET}")
                await client.close()
                return 0
            spinner.fail("Token invalid, re-authenticating")
        except Exception:
            spinner.fail("Token validation failed")
        finally:
            await client.close()
    
    print()
    print(f"  {C.DIM}Make sure you have:{C.RESET}")
    print(f"  {C.DIM}{DOT} Onboarded with the Truffle app{C.RESET}")
    print(f"  {C.DIM}{DOT} Your User ID from the recovery codes{C.RESET}")
    print()
    
    try:
        user_id = input(f"{C.CYAN}?{C.RESET} Enter your User ID: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        raise KeyboardInterrupt()
    if not user_id:
        error("User ID is required")
        return 1
    
    spinner = Spinner("Connecting to device")
    spinner.start()
    
    client = TruffleClient(address, token="")
    try:
        await client.connect()
        spinner.stop(success=True)
    except Exception as e:
        spinner.fail(f"Failed to connect: {e}")
        return 1
    
    print()
    info("Requesting authorization...")
    print(f"  {C.DIM}Please approve on your Truffle device{C.RESET}")
    
    spinner = Spinner("Waiting for approval")
    spinner.start()
    
    try:
        status, token = await client.register_new_session(user_id)
    except Exception as e:
        spinner.fail(f"Failed to register: {e}")
        await client.close()
        return 1
    
    await client.close()
    
    if status.error == NewSessionStatus.NEW_SESSION_SUCCESS and token:
        spinner.stop(success=True)
        storage.set_token(device_name, token)
        storage.set_last_used(device_name)
        print()
        success(f"Connected to {C.BOLD}{device_name}{C.RESET}")
        return 0
    elif status.error == NewSessionStatus.NEW_SESSION_TIMEOUT:
        spinner.fail("Approval timed out")
        return 1
    elif status.error == NewSessionStatus.NEW_SESSION_REJECTED:
        spinner.fail("Request was rejected")
        return 1
    else:
        spinner.fail(f"Authentication failed: {status.error}")
        return 1


def cmd_disconnect(args, storage: StorageService) -> int:
    target = args.target
    if target == "all":
        storage.clear_all()
        success("All device credentials cleared")
    else:
        if storage.remove_device(target):
            success(f"Disconnected from {C.BOLD}{target}{C.RESET}")
        else:
            error(f"No credentials found for {target}")
    return 0


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
    
    device = storage.state.last_used_device
    if not device:
        error("No device connected")
        print(f"  {C.DIM}Run: truffile connect <device>{C.RESET}")
        return 1
    
    token = storage.get_token(device)
    if not token:
        error(f"No token for {device}")
        print(f"  {C.DIM}Run: truffile connect {device}{C.RESET}")
        return 1
    
    spinner = Spinner(f"Resolving {device}")
    spinner.start()
    try:
        ip = await resolve_mdns(f"{device}.local")
        spinner.stop(success=True)
    except RuntimeError:
        spinner.fail(f"Could not resolve {device}.local")
        print(f"  {C.DIM}Try: ping {device}.local{C.RESET}")
        return 1
    
    address = f"{ip}:80"
    client = TruffleClient(address, token=token)
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


async def cmd_list_apps(storage: StorageService) -> int:
    device = storage.state.last_used_device
    if not device:
        error("No device connected")
        print(f"  {C.DIM}Run: truffile connect <device>{C.RESET}")
        return 1
    
    token = storage.get_token(device)
    if not token:
        error(f"No token for {device}")
        print(f"  {C.DIM}Run: truffile connect {device}{C.RESET}")
        return 1
    
    spinner = Spinner(f"Connecting to {device}")
    spinner.start()
    
    try:
        ip = await resolve_mdns(f"{device}.local")
    except RuntimeError as e:
        spinner.fail(str(e))
        return 1
    
    address = f"{ip}:80"
    client = TruffleClient(address, token=token)
    
    try:
        await client.connect()
        apps = await client.get_all_apps()
        spinner.stop(success=True)

        if not apps:
            print(f"  {C.DIM}No apps installed{C.RESET}")
            return 0

        focus_apps = [app for app in apps if app.HasField("foreground")]
        ambient_apps = [app for app in apps if app.HasField("background")]
        both_apps = [app for app in apps if app.HasField("foreground") and app.HasField("background")]

        print()
        if focus_apps:
            print(f"{C.BOLD}Focus Apps{C.RESET}")
            for app in focus_apps:
                print(f"  {C.CYAN}{DOT}{C.RESET} {app.metadata.name}")
                setattr(app.metadata, "description", getattr(app.metadata, "description", ""))
                if hasattr(app.metadata, "description") and app.metadata.description:
                    desc = app.metadata.description.strip().split('\n')[0][:55]
                    print(f"    {C.DIM}{desc}{C.RESET}")

        if ambient_apps:
            if focus_apps:
                print()
            print(f"{C.BOLD}Ambient Apps{C.RESET}")
            for app in ambient_apps:
                schedule = ""
                policy = app.background.runtime_policy
                if policy.HasField("interval"):
                    secs = policy.interval.duration.seconds
                    if secs >= 3600:
                        schedule = f"every {secs // 3600}h"
                    elif secs >= 60:
                        schedule = f"every {secs // 60}m"
                    else:
                        schedule = f"every {secs}s"
                elif policy.HasField("always"):
                    schedule = "always"
                print(f"  {C.CYAN}{DOT}{C.RESET} {app.metadata.name} {C.DIM}({schedule}){C.RESET}")
                setattr(app.metadata, "description", getattr(app.metadata, "description", ""))
                if hasattr(app.metadata, "description") and app.metadata.description:
                    desc = app.metadata.description.strip().split('\n')[0][:55]
                    print(f"    {C.DIM}{desc}{C.RESET}")

        print()
        print(
            f"{C.DIM}Total: {len(focus_apps)} focus, {len(ambient_apps)} ambient, "
            f"{len(both_apps)} both{C.RESET}"
        )
        return 0
        
    except Exception as e:
        spinner.fail(str(e))
        return 1
    finally:
        await client.close()

async def cmd_delete(args, storage: StorageService) -> int:
    device = storage.state.last_used_device
    if not device:
        error("No device connected")
        print(f"  {C.DIM}Run: truffile connect <device>{C.RESET}")
        return 1

    token = storage.get_token(device)
    if not token:
        error(f"No token for {device}")
        print(f"  {C.DIM}Run: truffile connect {device}{C.RESET}")
        return 1

    spinner = Spinner(f"Connecting to {device}")
    spinner.start()

    try:
        ip = await resolve_mdns(f"{device}.local")
    except RuntimeError as e:
        spinner.fail(str(e))
        return 1

    address = f"{ip}:80"
    client = TruffleClient(address, token=token)

    try:
        await client.connect()
        apps = await client.get_all_apps()
        spinner.stop(success=True)

        all_apps = []
        for app in apps:
            if app.HasField("foreground") and app.HasField("background"):
                kind = "both"
            elif app.HasField("foreground"):
                kind = "focus"
            elif app.HasField("background"):
                kind = "ambient"
            else:
                kind = "unknown"
            desc = app.metadata.description.strip().split('\n')[0][:55] if app.metadata.description else ""
            all_apps.append((kind, app.uuid, app.metadata.name, desc))

        if not all_apps:
            print(f"  {C.DIM}No apps installed{C.RESET}")
            return 0

        print()
        print(f"{C.BOLD}Installed Apps:{C.RESET}")
        print()
        for i, (kind, uuid, name, desc) in enumerate(all_apps, 1):
            print(f"  {C.CYAN}{i}.{C.RESET} {name} {C.DIM}({kind}){C.RESET}")
            if desc:
                print(f"     {C.DIM}{desc}{C.RESET}")
        print()

        try:
            choice = input(f"Select apps to delete (e.g. 1,3,5 or 'all'): ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0

        if not choice:
            return 0

        if choice.lower() == "all":
            to_delete = list(range(len(all_apps)))
        else:
            try:
                to_delete = [int(x.strip()) - 1 for x in choice.split(",")]
                for idx in to_delete:
                    if idx < 0 or idx >= len(all_apps):
                        error(f"Invalid selection: {idx + 1}")
                        return 1
            except ValueError:
                error("Invalid input")
                return 1

        print()
        deleted = 0
        for idx in to_delete:
            kind, uuid, name, _ = all_apps[idx]
            spinner = Spinner(f"Deleting {name}")
            spinner.start()
            try:
                await client.delete_app(uuid)
                spinner.stop(success=True)
                deleted += 1
            except Exception as e:
                spinner.fail(f"Failed to delete {name}: {e}")

        print()
        success(f"Deleted {deleted} app(s)")
        return 0

    except Exception as e:
        spinner.fail(str(e))
        return 1
    finally:
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

def run_async(coro):
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        print(f"\r{C.RED}{CROSS} Cancelled{C.RESET}        ")
        return 130


def cmd_list(args, storage: StorageService) -> int:
    what = args.what
    if what == "apps":
        return run_async(cmd_list_apps(storage))
    elif what == "devices":
        devices = storage.list_devices()
        if not devices:
            print(f"  {C.DIM}No connected devices{C.RESET}")
        else:
            print(f"{C.BOLD}Connected Devices{C.RESET}")
            for d in devices:
                if d == storage.state.last_used_device:
                    print(f"  {C.GREEN}{DOT}{C.RESET} {d} {C.DIM}(active){C.RESET}")
                else:
                    print(f"  {C.CYAN}{DOT}{C.RESET} {d}")
    return 0


async def cmd_models(storage: StorageService) -> int:
    """List IF2 models on the connected device."""
    device = storage.state.last_used_device
    if not device:
        error("No device connected")
        print(f"  {C.DIM}Run: truffile connect <device>{C.RESET}")
        return 1
    
    spinner = Spinner(f"Connecting to {device}")
    spinner.start()
    
    try:
        ip = await resolve_mdns(f"{device}.local")
    except RuntimeError:
        spinner.fail(f"Could not resolve {device}.local")
        return 1

    try:
        url = f"http://{ip}/if2/v1/models"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
        spinner.stop(success=True)
    except Exception as e:
        spinner.fail(f"Failed to get IF2 models: {e}")
        return 1

    models = payload.get("data", [])
    if not isinstance(models, list):
        spinner.fail("Invalid response: missing 'data' list")
        return 1

    print()
    print(f"{MUSHROOM} {C.BOLD}IF2 Models on {device}{C.RESET}")
    print()

    if not models:
        print(f"  {C.DIM}No models found{C.RESET}")
        return 0

    for m in models:
        if not isinstance(m, dict):
            continue
        model_id = m.get("id", "<unknown>")
        name = m.get("name", model_id)
        uuid = m.get("uuid", "<none>")
        ctx = m.get("context_length", "<unknown>")
        arch = m.get("architecture", {})
        tokenizer = arch.get("tokenizer", "<unknown>") if isinstance(arch, dict) else "<unknown>"
        max_batch = m.get("max_batch_size", "<unknown>")
        print(f"  {C.GREEN}{CHECK}{C.RESET} {name}")
        print(f"    {C.DIM}id: {model_id}{C.RESET}")
        print(f"    {C.DIM}uuid: {uuid}{C.RESET}")
        print(f"    {C.DIM}context: {ctx}, tokenizer: {tokenizer}, max_batch: {max_batch}{C.RESET}")

    return 0


async def _resolve_connected_device(storage: StorageService) -> tuple[str, str] | tuple[None, None]:
    device = storage.state.last_used_device
    if not device:
        error("No device connected")
        print(f"  {C.DIM}Run: truffile connect <device>{C.RESET}")
        return None, None
    try:
        ip = await resolve_mdns(f"{device}.local")
    except RuntimeError:
        error(f"Could not resolve {device}.local")
        return None, None
    return device, ip


async def _default_model(ip: str) -> str | None:
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"http://{ip}/if2/v1/models")
            resp.raise_for_status()
            payload = resp.json()
        models = payload.get("data", [])
        if not isinstance(models, list) or not models:
            return None
        first = models[0]
        if not isinstance(first, dict):
            return None
        return str(first.get("uuid") or first.get("id") or "")
    except Exception:
        return None


async def cmd_chat(args, storage: StorageService) -> int:
    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return 1

    prompt = args.prompt
    if not prompt and args.prompt_words:
        prompt = " ".join(args.prompt_words).strip()
    if not prompt:
        error("Missing prompt")
        print(f"  {C.DIM}Usage: truffile chat --prompt \"hello\"{C.RESET}")
        print(f"  {C.DIM}Or:    truffile chat \"hello\"{C.RESET}")
        return 1

    model = args.model
    if not model:
        spinner = Spinner("Resolving default model")
        spinner.start()
        model = await _default_model(ip)
        if not model:
            spinner.fail("Failed to resolve default model from IF2")
            return 1
        spinner.stop(success=True)

    stream = not args.no_stream and not args.json
    messages: list[dict[str, str]] = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "reasoning": {"enabled": bool(args.reasoning)},
    }
    if args.max_tokens is not None:
        payload["max_tokens"] = args.max_tokens
    else:
        payload["max_tokens"] = 512
    if args.temperature is not None:
        payload["temperature"] = args.temperature
    if args.top_p is not None:
        payload["top_p"] = args.top_p
    if stream:
        payload["stream_options"] = {"include_usage": True}

    url = f"http://{ip}/if2/v1/chat/completions"
    headers = {"Content-Type": "application/json"}

    spinner = Spinner(f"Connecting to {device}")
    spinner.start()
    try:
        with httpx.Client(timeout=None) as client:
            if stream:
                with client.stream("POST", url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    spinner.stop(success=True)
                    usage_printed = False
                    for raw in resp.iter_lines():
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

                        choices = evt.get("choices")
                        if isinstance(choices, list) and choices:
                            c0 = choices[0]
                            if isinstance(c0, dict):
                                delta = c0.get("delta", {})
                                if isinstance(delta, dict):
                                    txt = delta.get("content")
                                    if isinstance(txt, str) and txt:
                                        print(txt, end="", flush=True)
                                    reasoning = delta.get("reasoning")
                                    if args.reasoning and isinstance(reasoning, str) and reasoning:
                                        print(reasoning, end="", flush=True)

                        usage = evt.get("usage")
                        if isinstance(usage, dict) and not usage_printed:
                            usage_printed = True
                            print(f"\n{C.DIM}[usage] {usage}{C.RESET}", flush=True)
                    print()
            else:
                resp = client.post(url, headers=headers, json=payload, timeout=120.0)
                resp.raise_for_status()
                spinner.stop(success=True)
                body = resp.json()
                if args.json:
                    print(json.dumps(body, indent=2))
                else:
                    content = ""
                    try:
                        choices = body.get("choices", [])
                        if isinstance(choices, list) and choices:
                            msg = choices[0].get("message", {})
                            if isinstance(msg, dict):
                                content = str(msg.get("content", ""))
                    except Exception:
                        content = ""
                    print(content)
        return 0
    except Exception as e:
        spinner.fail(f"Chat request failed: {e}")
        return 1


def _inject_reasoning_into_chunk(chunk: dict, state: dict) -> dict:
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return chunk
    c0 = choices[0]
    if not isinstance(c0, dict):
        return chunk
    delta = c0.get("delta")
    if not isinstance(delta, dict):
        return chunk

    reasoning = delta.get("reasoning")
    content = delta.get("content")
    merged = ""

    if isinstance(reasoning, str) and reasoning:
        if not state.get("thinking_open", False):
            merged += "<think>\n"
            state["thinking_open"] = True
        merged += reasoning

    if isinstance(content, str) and content:
        if state.get("thinking_open", False):
            merged += "\n</think>\n"
            state["thinking_open"] = False
        merged += content

    if merged:
        delta["content"] = merged
    if "reasoning" in delta:
        del delta["reasoning"]
    return chunk


def _inject_reasoning_into_response(body: dict) -> dict:
    choices = body.get("choices")
    if not isinstance(choices, list):
        return body
    for c in choices:
        if not isinstance(c, dict):
            continue
        msg = c.get("message")
        if not isinstance(msg, dict):
            continue
        reasoning = msg.get("reasoning")
        content = msg.get("content", "")
        if isinstance(reasoning, str) and reasoning:
            content_text = content if isinstance(content, str) else str(content)
            msg["content"] = f"<think>\n{reasoning}\n</think>\n{content_text}"
        if "reasoning" in msg:
            del msg["reasoning"]
    return body


async def cmd_proxy(args, storage: StorageService) -> int:
    device = args.device if args.device else storage.state.last_used_device
    if not device:
        error("No device specified or connected")
        print(f"  {C.DIM}Run: truffile connect <device>{C.RESET}")
        print(f"  {C.DIM}Or:  truffile proxy --device <device>{C.RESET}")
        return 1

    spinner = Spinner(f"Resolving {device}.local")
    spinner.start()
    try:
        ip = await resolve_mdns(f"{device}.local")
        spinner.stop(success=True)
    except RuntimeError:
        spinner.fail(f"Could not resolve {device}.local")
        return 1

    target_base = f"http://{ip}"
    host = args.host
    port = args.port
    include_think_tags = not args.no_think_tags

    class ProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format, *_args):
            return

        def _send_json(self, code: int, body: dict):
            raw = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _map_path(self, path: str) -> str | None:
            if path == "/v1/models":
                return "/if2/v1/models"
            if path == "/v1/chat/completions":
                return "/if2/v1/chat/completions"
            return None

        def _forward_headers(self) -> dict[str, str]:
            out: dict[str, str] = {"Content-Type": "application/json"}
            auth = self.headers.get("Authorization")
            if auth:
                out["Authorization"] = auth
            return out

        def do_GET(self):
            mapped = self._map_path(self.path)
            if not mapped:
                self._send_json(404, {"error": {"message": "Not found"}})
                return

            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(f"{target_base}{mapped}", headers=self._forward_headers())
                self.send_response(resp.status_code)
                self.send_header("Content-Type", resp.headers.get("content-type", "application/json"))
                self.send_header("Content-Length", str(len(resp.content)))
                self.end_headers()
                self.wfile.write(resp.content)
            except Exception as e:
                self._send_json(502, {"error": {"message": f"Upstream GET failed: {e}"}})

        def do_POST(self):
            mapped = self._map_path(self.path)
            if not mapped:
                self._send_json(404, {"error": {"message": "Not found"}})
                return

            raw_body = b""
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_len) if content_len > 0 else b"{}"
                body = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self._send_json(400, {"error": {"message": f"Invalid JSON body: {e}"}})
                return

            if mapped == "/if2/v1/chat/completions":
                if "reasoning" not in body:
                    body["reasoning"] = {"enabled": False}

            stream_mode = bool(body.get("stream")) and mapped == "/if2/v1/chat/completions"

            try:
                with httpx.Client(timeout=None) as client:
                    if stream_mode:
                        with client.stream(
                            "POST",
                            f"{target_base}{mapped}",
                            headers=self._forward_headers(),
                            json=body,
                        ) as resp:
                            self.send_response(resp.status_code)
                            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                            self.send_header("Cache-Control", "no-cache")
                            self.send_header("Connection", "keep-alive")
                            self.end_headers()

                            state = {"thinking_open": False}
                            for raw_line in resp.iter_lines():
                                line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", errors="replace")
                                if not line:
                                    self.wfile.write(b"\n")
                                    self.wfile.flush()
                                    continue
                                if line.startswith("data:"):
                                    payload = line[5:].strip()
                                    if payload == "[DONE]":
                                        if include_think_tags and state.get("thinking_open", False):
                                            close_evt = {
                                                "choices": [{"delta": {"content": "\n</think>\n"}, "index": 0}]
                                            }
                                            out = f"data: {json.dumps(close_evt, separators=(',', ':'))}\n\n"
                                            self.wfile.write(out.encode("utf-8"))
                                        self.wfile.write(b"data: [DONE]\n\n")
                                        self.wfile.flush()
                                        break
                                    try:
                                        evt = json.loads(payload)
                                        if include_think_tags:
                                            evt = _inject_reasoning_into_chunk(evt, state)
                                        out = f"data: {json.dumps(evt, separators=(',', ':'))}\n\n"
                                    except Exception:
                                        out = f"{line}\n\n"
                                    self.wfile.write(out.encode("utf-8"))
                                else:
                                    self.wfile.write((line + "\n").encode("utf-8"))
                                self.wfile.flush()
                    else:
                        resp = client.post(
                            f"{target_base}{mapped}",
                            headers=self._forward_headers(),
                            json=body,
                            timeout=120.0,
                        )
                        content = resp.content
                        if (
                            mapped == "/if2/v1/chat/completions"
                            and include_think_tags
                            and "application/json" in resp.headers.get("content-type", "")
                        ):
                            try:
                                parsed = json.loads(content.decode("utf-8"))
                                parsed = _inject_reasoning_into_response(parsed)
                                content = json.dumps(parsed).encode("utf-8")
                            except Exception:
                                pass
                        self.send_response(resp.status_code)
                        self.send_header("Content-Type", resp.headers.get("content-type", "application/json"))
                        self.send_header("Content-Length", str(len(content)))
                        self.end_headers()
                        self.wfile.write(content)
            except Exception as e:
                self._send_json(502, {"error": {"message": f"Upstream POST failed: {e}"}})

    print(f"{MUSHROOM} {C.BOLD}truffile proxy{C.RESET}")
    print()
    print(f"  {C.DIM}Device:{C.RESET} {device} ({ip})")
    print(f"  {C.DIM}Listen:{C.RESET} http://{host}:{port}")
    print(f"  {C.DIM}Upstream:{C.RESET} {target_base}/if2/v1/*")
    print(f"  {C.DIM}Reasoning tags:{C.RESET} {'on' if include_think_tags else 'off'}")
    print()
    print(f"  {C.DIM}OpenAI-compatible base URL:{C.RESET}")
    print(f"    {C.CYAN}http://{host}:{port}/v1{C.RESET}")
    print()
    print(f"  {C.DIM}Press Ctrl+C to stop{C.RESET}")
    print()

    try:
        server = ThreadingHTTPServer((host, port), ProxyHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"{C.RED}{CROSS} Cancelled{C.RESET}")
        return 130
    except OSError as e:
        error(f"Could not start proxy: {e}")
        return 1

    return 0


async def cmd_scan(args, storage: StorageService) -> int:
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf, IPVersion
    except ImportError:
        error("zeroconf package required for scanning")
        print(f"  {C.DIM}pip install zeroconf{C.RESET}")
        return 1
    
    devices: dict[str, dict] = {}
    scan_done = asyncio.Event()
    
    class TruffleListener(ServiceListener):
        def add_service(self, zc: Zeroconf, type_: str, name: str):
            if name.lower().startswith("truffle-"):
                info = zc.get_service_info(type_, name)
                device_name = name.split(".")[0]
                if info and device_name not in devices:
                    addresses = [addr for addr in info.parsed_addresses(IPVersion.V4Only)]
                    devices[device_name] = {
                        "name": device_name,
                        "addresses": addresses,
                        "port": info.port,
                    }
        
        def remove_service(self, zc: Zeroconf, type_: str, name: str):
            pass
        
        def update_service(self, zc: Zeroconf, type_: str, name: str):
            pass
    
    timeout = args.timeout if hasattr(args, 'timeout') else 5
    
    spinner = Spinner(f"Scanning for Truffle devices ({timeout}s)")
    spinner.start()
    
    try:
        zc = Zeroconf(ip_version=IPVersion.V4Only)
        listener = TruffleListener()
        
        browsers = [
            ServiceBrowser(zc, "_truffle._tcp.local.", listener),
        ]
        
        await asyncio.sleep(timeout)
        
        for browser in browsers:
            browser.cancel()
        zc.close()
        
    except Exception as e:
        spinner.fail(f"Scan failed: {e}")
        return 1
    
    spinner.stop(success=True)
    
    if not devices:
        print()
        print(f"  {C.DIM}No Truffle devices found on the network{C.RESET}")
        print()
        print(f"  {C.DIM}Make sure your Truffle is:{C.RESET}")
        print(f"    {C.DIM}• Powered on{C.RESET}")
        print(f"    {C.DIM}• Connected to the same network as this computer{C.RESET}")
        print()
        return 1
    
    print()
    print(f"{C.BOLD}Found {len(devices)} Truffle device(s):{C.RESET}")
    print()
    
    device_list = list(devices.values())
    for i, device in enumerate(device_list, 1):
        name = device["name"]
        addrs = ", ".join(device["addresses"]) if device["addresses"] else "unknown"
        
        already_connected = storage.get_token(name) is not None
        if already_connected:
            print(f"  {C.GREEN}{i}.{C.RESET} {C.BOLD}{name}{C.RESET} {C.DIM}({addrs}){C.RESET} {C.GREEN}[connected]{C.RESET}")
        else:
            print(f"  {C.CYAN}{i}.{C.RESET} {C.BOLD}{name}{C.RESET} {C.DIM}({addrs}){C.RESET}")
    
    print()
    
    try:
        choice = input(f"Select device to connect (1-{len(device_list)}) or press Enter to cancel: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return 0
    
    if not choice:
        return 0
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(device_list):
            selected = device_list[idx]
            print()
            
            class FakeArgs:
                device = selected["name"]
            
            return await cmd_connect(FakeArgs(), storage)
        else:
            error("Invalid selection")
            return 1
    except ValueError:
        error("Invalid input")
        return 1


def cmd_validate(args) -> int:
    app_dir = Path(args.path).resolve()
    if not app_dir.exists() or not app_dir.is_dir():
        error(f"{app_dir} is not a valid directory")
        return 1

    info(f"Validating app in {app_dir.name}")
    valid, _config, app_type, warnings, errors = validate_app_dir(app_dir)
    for w in warnings:
        warn(w)
    if not valid:
        for e in errors:
            error(e)
        return 1

    success(f"Validation passed ({app_type})")
    return 0


def print_help():
    print(f"{MUSHROOM} {C.BOLD}truffile{C.RESET} - TruffleOS SDK")
    print()
    print(f"{C.BOLD}Usage:{C.RESET} truffile <command> [options]")
    print()
    print(f"{C.BOLD}Commands:{C.RESET}")
    print(f"  {C.BLUE}scan{C.RESET}                      Scan network for Truffle devices")
    print(f"  {C.BLUE}connect{C.RESET} <device>         Connect to a Truffle device")
    print(f"  {C.BLUE}disconnect{C.RESET} <device|all>  Disconnect and clear credentials")
    print(f"  {C.BLUE}deploy{C.RESET} [path]            Deploy an app (reads type from truffile.yaml)")
    print(f"  {C.BLUE}validate{C.RESET} [path]          Validate app config and files")
    print(f"  {C.BLUE}delete{C.RESET}                    Delete installed apps from device")
    print(f"  {C.BLUE}list{C.RESET} <apps|devices>      List installed apps or devices")
    print(f"  {C.BLUE}models{C.RESET}                    List IF2 models on connected device")
    print(f"  {C.BLUE}chat{C.RESET} [prompt]            Chat with IF2 model on connected device")
    print(f"  {C.BLUE}proxy{C.RESET}                    Run OpenAI-compatible IF2 proxy")
    print()
    print(f"{C.BOLD}Examples:{C.RESET}")
    print(f"  {C.DIM}truffile scan{C.RESET}                {C.DIM}# find devices on network{C.RESET}")
    print(f"  {C.DIM}truffile connect truffle-6272{C.RESET}")
    print(f"  {C.DIM}truffile deploy ./my-app{C.RESET}")
    print(f"  {C.DIM}truffile deploy --dry-run ./my-app{C.RESET}")
    print(f"  {C.DIM}truffile deploy{C.RESET}              {C.DIM}# uses current directory{C.RESET}")
    print(f"  {C.DIM}truffile validate ./my-app{C.RESET}")
    print(f"  {C.DIM}truffile list apps{C.RESET}")
    print(f"  {C.DIM}truffile models{C.RESET}              {C.DIM}# show IF2 models{C.RESET}")
    print(f"  {C.DIM}truffile chat \"hello\"{C.RESET}       {C.DIM}# run IF2 chat completion{C.RESET}")
    print(f"  {C.DIM}truffile proxy{C.RESET}               {C.DIM}# run local /v1 proxy{C.RESET}")
    print()


def main() -> int:
    if len(sys.argv) == 1 or sys.argv[1] in ("-h", "--help"):
        print_help()
        return 0
    
    parser = argparse.ArgumentParser(
        prog="truffile",
        description="truffile - TruffleOS SDK CLI",
        add_help=False,
    )
    subparsers = parser.add_subparsers(dest="command")

    p_scan = subparsers.add_parser("scan", add_help=False)
    p_scan.add_argument("-t", "--timeout", type=int, default=5, help="Scan timeout in seconds")

    p_connect = subparsers.add_parser("connect", add_help=False)
    p_connect.add_argument("device", nargs="?")

    p_disconnect = subparsers.add_parser("disconnect", add_help=False)
    p_disconnect.add_argument("target", nargs="?")

    p_deploy = subparsers.add_parser("deploy", add_help=False)
    p_deploy.add_argument("path", nargs="?", default=".")
    p_deploy.add_argument("-i", "--interactive", action="store_true", help="Interactive terminal mode")
    p_deploy.add_argument("--dry-run", action="store_true", help="Show deploy plan without mutating device")

    p_validate = subparsers.add_parser("validate", add_help=False)
    p_validate.add_argument("path", nargs="?", default=".")

    p_delete = subparsers.add_parser("delete", add_help=False)

    p_list = subparsers.add_parser("list", add_help=False)
    p_list.add_argument("what", choices=["apps", "devices"], nargs="?")

    p_models = subparsers.add_parser("models", add_help=False)
    
    p_chat = subparsers.add_parser("chat", add_help=False)
    p_chat.add_argument("prompt_words", nargs="*", help="Prompt text (alternative to --prompt)")
    p_chat.add_argument("-p", "--prompt", help="Prompt text")
    p_chat.add_argument("-m", "--model", help="Model id/uuid (default: first model from IF2 list)")
    p_chat.add_argument("--system", help="System prompt")
    p_chat.add_argument("--reasoning", action="store_true", help="Enable reasoning mode")
    p_chat.add_argument("--max-tokens", type=int, help="Max response tokens")
    p_chat.add_argument("--temperature", type=float, help="Sampling temperature")
    p_chat.add_argument("--top-p", type=float, help="Nucleus sampling top-p")
    p_chat.add_argument("--no-stream", action="store_true", help="Disable streaming output")
    p_chat.add_argument("--json", action="store_true", help="Print full JSON response (non-stream)")
    
    p_proxy = subparsers.add_parser("proxy", add_help=False)
    p_proxy.add_argument("--device", "-d", help="Device name (default: last connected)")
    p_proxy.add_argument("--host", default="127.0.0.1", help="Host to bind")
    p_proxy.add_argument("--port", "-p", type=int, default=8080, help="Port to bind")
    p_proxy.add_argument("--no-think-tags", action="store_true", help="Do not inject <think> tags")

    args = parser.parse_args()

    if args.command is None:
        print_help()
        return 0
    
    if args.command == "connect":
        if not args.device:
            error("Missing device name")
            print(f"  {C.DIM}Usage: truffile connect <device>{C.RESET}")
            return 1
    elif args.command == "disconnect":
        if not args.target:
            error("Missing device name")
            print(f"  {C.DIM}Usage: truffile disconnect <device|all>{C.RESET}")
            return 1
    elif args.command == "list":
        if not args.what:
            error("Missing argument")
            print(f"  {C.DIM}Usage: truffile list <apps|devices>{C.RESET}")
            return 1

    storage = StorageService()

    if args.command == "scan":
        return run_async(cmd_scan(args, storage))
    elif args.command == "connect":
        return run_async(cmd_connect(args, storage))
    elif args.command == "disconnect":
        return cmd_disconnect(args, storage)
    elif args.command == "delete":
        return run_async(cmd_delete(args, storage))
    elif args.command == "deploy":
        return run_async(cmd_deploy(args, storage))
    elif args.command == "list":
        return cmd_list(args, storage)
    elif args.command == "models":
        return run_async(cmd_models(storage))
    elif args.command == "chat":
        return run_async(cmd_chat(args, storage))
    elif args.command == "proxy":
        return run_async(cmd_proxy(args, storage))
    elif args.command == "validate":
        return cmd_validate(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
