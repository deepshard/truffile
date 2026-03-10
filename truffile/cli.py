import argparse
import asyncio
import json
import os
import re
import select
import signal
import socket
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

import httpx
from truffile.storage import StorageService
from truffile.client import TruffleClient, resolve_mdns, NewSessionStatus
from truffile.schema import validate_app_dir
from truffile.deploy import build_deploy_plan, deploy_with_builder

try:
    import readline
except Exception:
    readline = None  # type: ignore[assignment]

try:
    import termios
    import tty
except Exception:
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]


# ANSI colors
class C:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
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
HAMMER = "🔨"
TOOL_TAGS = ("<toolcall>", "</toolcall>")
TOOL_TAG_PATTERN = re.compile(r"<toolcall>\s*(.*?)\s*</toolcall>", re.DOTALL)
REPL_COMMANDS = [
    "/help",
    "/",
    "/history",
    "/reset",
    "/models",
    "/config",
    "/reasoning",
    "/stream",
    "/json",
    "/tools",
    "/max_tokens",
    "/temperature",
    "/top_p",
    "/max_rounds",
    "/system",
    "/mcp",
    "/exit",
    "/quit",
]


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


class MushroomPulse:
    FRAMES = ["(🍄   )", "(🍄.  )", "(🍄.. )", "(🍄...)", "(🍄 ..)", "(🍄  .)"]

    def __init__(self, message: str = "thinking", interval: float = 0.09):
        self.message = message
        self.interval = interval
        self.running = False
        self.thread: threading.Thread | None = None
        self.frame_idx = 0
        self.enabled = bool(sys.stdout.isatty())

    def _spin(self) -> None:
        while self.running:
            frame = self.FRAMES[self.frame_idx % len(self.FRAMES)]
            sys.stdout.write(f"\r{C.MAGENTA}{frame}{C.RESET} {C.DIM}{self.message}{C.RESET}")
            sys.stdout.flush()
            self.frame_idx += 1
            time.sleep(self.interval)

    def start(self) -> None:
        if not self.enabled or self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        sys.stdout.write("\r\033[K")
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
    """List models on your Truffle."""
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


def _model_display_name(model: dict[str, Any]) -> str:
    model_id = str(model.get("id") or "<unknown>")
    name = str(model.get("name") or model_id)
    if name == model_id:
        return name
    return f"{name} ({model_id})"


def _model_value(model: dict[str, Any]) -> str:
    return str(model.get("uuid") or model.get("id") or "")


def _model_matches_current(model: dict[str, Any], current_model: str) -> bool:
    if not current_model:
        return False
    mv = _model_value(model)
    mid = str(model.get("id") or "")
    return current_model in {mv, mid}


def _pick_model_with_numbers(models: list[dict[str, Any]], current_model: str) -> str | None:
    if not models:
        return None
    print(f"{C.BLUE}models:{C.RESET}")
    default_idx = 0
    for i, m in enumerate(models, start=1):
        active = f" {C.DIM}[active]{C.RESET}" if _model_matches_current(m, current_model) else ""
        if active:
            default_idx = i - 1
        print(f"{C.BLUE}{i}.{C.RESET} {_model_display_name(m)}{active}")
    choice = input(f"{C.CYAN}?{C.RESET} select model [1-{len(models)}] (Enter to keep): ").strip()
    if not choice:
        return _model_value(models[default_idx])
    try:
        idx = int(choice) - 1
    except ValueError:
        warn("invalid model selection")
        return None
    if idx < 0 or idx >= len(models):
        warn("invalid model selection")
        return None
    return _model_value(models[idx])


def _pick_model_interactive(models: list[dict[str, Any]], current_model: str) -> str | None:
    if not models:
        return None
    if not sys.stdin.isatty() or not sys.stdout.isatty() or termios is None or tty is None:
        return _pick_model_with_numbers(models, current_model)

    selected = 0
    for i, m in enumerate(models):
        if _model_matches_current(m, current_model):
            selected = i
            break

    lines_rendered = 0

    def _render() -> None:
        nonlocal lines_rendered
        lines: list[str] = []
        lines.append(f"{C.BLUE}select model (↑/↓, Enter=select, q=cancel){C.RESET}")
        for i, m in enumerate(models):
            pointer = "›" if i == selected else " "
            active = f" {C.DIM}[active]{C.RESET}" if _model_matches_current(m, current_model) else ""
            line = f" {C.CYAN}{pointer}{C.RESET} {_model_display_name(m)}{active}"
            lines.append(line)

        if lines_rendered > 0:
            sys.stdout.write(f"\033[{lines_rendered}A")
        for line in lines:
            sys.stdout.write(f"\r\033[K{line}\n")
        sys.stdout.flush()
        lines_rendered = len(lines)

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        _render()
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                sys.stdout.write("\r\033[K")
                return _model_value(models[selected])
            if ch in ("q", "Q"):
                sys.stdout.write("\r\033[K")
                return None
            if ch == "\x1b":
                seq1 = sys.stdin.read(1)
                if seq1 == "[":
                    seq2 = sys.stdin.read(1)
                    if seq2 == "A":
                        selected = (selected - 1) % len(models)
                        _render()
                        continue
                    if seq2 == "B":
                        selected = (selected + 1) % len(models)
                        _render()
                        continue
                return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        if lines_rendered > 0:
            sys.stdout.write(f"\033[{lines_rendered}A")
            for _ in range(lines_rendered):
                sys.stdout.write("\r\033[K\n")
            sys.stdout.write(f"\033[{lines_rendered}A")
        sys.stdout.flush()


def _fetch_models_payload(client: httpx.Client, ip: str) -> list[dict[str, Any]]:
    resp = client.get(f"http://{ip}/if2/v1/models", timeout=15.0)
    resp.raise_for_status()
    payload = resp.json()
    raw = payload.get("data", [])
    if not isinstance(raw, list):
        raise RuntimeError("invalid models payload")
    out: list[dict[str, Any]] = []
    for m in raw:
        if isinstance(m, dict):
            out.append(m)
    return out


@dataclass
class ChatSettings:
    model: str
    system_prompt: str | None = None
    reasoning: bool = True
    stream: bool = True
    json_mode: bool = False
    max_tokens: int = 512
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
            await group.__aexit__(None, None, None)
            raise
        self._group = group
        self.endpoint = endpoint

    async def disconnect(self) -> None:
        if self._group is None:
            self.endpoint = None
            return
        await self._group.__aexit__(None, None, None)
        self._group = None
        self.endpoint = None

    def list_tool_names(self) -> list[str]:
        if self._group is None:
            return []
        return sorted(self._group.tools.keys())

    def build_openai_tools(self) -> list[dict[str, Any]]:
        if self._group is None:
            return []
        out: list[dict[str, Any]] = []
        for name, tool in sorted(self._group.tools.items(), key=lambda kv: kv[0]):
            params = tool.inputSchema if isinstance(tool.inputSchema, dict) else {"type": "object", "properties": {}}
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": str(tool.description or f"MCP tool {name}"),
                        "parameters": params,
                    },
                }
            )
        return out

    def has_tool(self, name: str) -> bool:
        if self._group is None:
            return False
        return name in self._group.tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._group is None:
            return {"error": "mcp not connected"}
        try:
            result = await self._group.call_tool(name=name, arguments=arguments)
            content: list[dict[str, Any]] = []
            for part in result.content:
                if hasattr(part, "model_dump"):
                    content.append(part.model_dump())  # type: ignore[call-arg]
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


def _print_repl_commands(prefix: str | None = None) -> None:
    if prefix is None:
        matches = REPL_COMMANDS
    else:
        matches = [cmd for cmd in REPL_COMMANDS if cmd.startswith(prefix)]
    if not matches:
        print(f"{C.YELLOW}no command matches: {prefix}{C.RESET}")
        return
    print(f"{C.BLUE}commands: {', '.join(matches)}{C.RESET}")


def _install_repl_completer(commands: list[str]) -> Callable[[], None] | None:
    if readline is None:
        return None
    try:
        prev_completer = readline.get_completer()
        prev_delims = readline.get_completer_delims()
        prev_display_hook = getattr(readline, "get_completion_display_matches_hook", lambda: None)()
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set show-all-if-ambiguous on")
        readline.parse_and_bind("set completion-ignore-case on")
        readline.set_completer_delims(" \t\n")
        matches: list[str] = []

        def _complete(text: str, state: int) -> str | None:
            nonlocal matches
            if state == 0:
                buffer = readline.get_line_buffer().lstrip()
                if buffer.startswith("/"):
                    prefix = buffer.split()[0]
                    matches = [cmd for cmd in commands if cmd.startswith(prefix)]
                else:
                    matches = []
            if state < len(matches):
                return matches[state]
            return None

        readline.set_completer(_complete)
        if hasattr(readline, "set_completion_display_matches_hook"):
            def _display_matches(substitution: str, display_matches: list[str], longest_match_length: int) -> None:
                del substitution, longest_match_length
                if not display_matches:
                    return
                print()
                print(f"{C.BLUE}commands: {', '.join(display_matches)}{C.RESET}")
                try:
                    readline.redisplay()
                except Exception:
                    pass
            readline.set_completion_display_matches_hook(_display_matches)

        def _cleanup() -> None:
            try:
                readline.set_completer(prev_completer)
                readline.set_completer_delims(prev_delims)
                if hasattr(readline, "set_completion_display_matches_hook"):
                    readline.set_completion_display_matches_hook(prev_display_hook)
            except Exception:
                pass

        return _cleanup
    except Exception:
        return None


class StreamAbortWatcher:
    def __init__(self) -> None:
        self.enabled = bool(sys.stdin.isatty() and termios is not None and tty is not None)
        self._fd: int | None = None
        self._old_attrs: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._abort_reason: str | None = None

    def __enter__(self) -> "StreamAbortWatcher":
        if not self.enabled:
            return self
        try:
            self._fd = sys.stdin.fileno()
            self._old_attrs = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        except Exception:
            self.enabled = False
            return self
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()
        return self

    def _watch(self) -> None:
        if self._fd is None:
            return
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([self._fd], [], [], 0.1)
            except Exception:
                return
            if not ready:
                continue
            try:
                ch = os.read(self._fd, 1)
            except Exception:
                continue
            if not ch:
                continue
            if ch == b"\x1b":
                self._abort_reason = "esc"
                self._stop.set()
                return

    def aborted(self) -> bool:
        return self._abort_reason is not None

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.2)
        if self.enabled and self._fd is not None and self._old_attrs is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)
            except Exception:
                pass
        return False


def _run_single_chat_request(
    *,
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    settings: ChatSettings,
    stream: bool,
) -> tuple[dict[str, Any], dict[str, Any] | None, bool]:
    wait_anim = MushroomPulse("thinking")
    wait_anim.start()
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
                        if not first_event_seen:
                            wait_anim.stop()
                            first_event_seen = True

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
                            reasoning_parts.append(reasoning_chunk)
                            if settings.reasoning:
                                if not reasoning_stream_started:
                                    print(f"{C.GRAY}thinking:{C.RESET}")
                                    reasoning_stream_started = True
                                print(f"{C.GRAY}{reasoning_chunk}{C.RESET}", end="", flush=True)

                        content_chunk = delta.get("content")
                        if isinstance(content_chunk, str) and content_chunk:
                            content_parts.append(content_chunk)
                            if not settings.reasoning:
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
            wait_anim.stop()

        msg: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts).strip()}
        reasoning_text = "".join(reasoning_parts).strip()
        if reasoning_text:
            msg["reasoning_content"] = reasoning_text
        if tool_calls_by_index:
            msg["tool_calls"] = [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)]
        if settings.reasoning:
            if reasoning_stream_started:
                print()
            response_text = str(msg.get("content") or "")
            if response_text:
                print()
                print(response_text)
        elif content_parts:
            print()
        if interrupted:
            print(f"{C.YELLOW}response interrupted{C.RESET}")
        return msg, usage, interrupted

    try:
        resp = client.post(url, headers=headers, json=payload, timeout=120.0)
        resp.raise_for_status()
        body = resp.json()
    finally:
        wait_anim.stop()
    if settings.json_mode:
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
    user_text: str,
) -> int:
    messages.append({"role": "user", "content": user_text})

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
            client=client, url=url, headers=headers, payload=payload, settings=settings, stream=stream
        )
        messages.append(assistant_msg)
        if isinstance(usage, dict):
            print(f"{C.DIM}[usage] {usage}{C.RESET}")
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
                print(f"{C.CYAN}{HAMMER} tool{C.RESET} {name}")
                tool_result = _execute_default_tool(name, parsed_args)
            elif mcp_client.has_tool(name):
                print(f"{C.CYAN}{HAMMER} mcp{C.RESET} {name}")
                tool_result = await mcp_client.call_tool(name, parsed_args)
            else:
                print(f"{C.YELLOW}{WARN} unknown tool{C.RESET} {name}")
                tool_result = {"error": f"unknown tool '{name}'"}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )

    warn("Reached max tool rounds without a final assistant response")
    return 1


async def cmd_chat(args, storage: StorageService) -> int:
    prompt = ""

    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return 1

    spinner = Spinner("Resolving default model")
    spinner.start()
    model = await _default_model(ip)
    if not model:
        spinner.fail("Failed to resolve default model from IF2")
        return 1
    spinner.stop(success=True)

    settings = ChatSettings(model=model)
    mcp_client = ChatMCPClient()
    messages: list[dict[str, Any]] = []

    url = f"http://{ip}/if2/v1/chat/completions"
    headers = {"Content-Type": "application/json"}

    try:
        spinner = Spinner(f"Connecting to {device}")
        spinner.start()
        with httpx.Client(timeout=None) as client:
            spinner.stop(success=True)

            # REPL mode (default).
            print(f"{C.DIM}model: {settings.model}{C.RESET}")
            print(
                f"{C.DIM}commands: /help, /history, /reset, /models, /config, /mcp, /exit{C.RESET}"
            )

            cleanup_repl = _install_repl_completer(REPL_COMMANDS)
            try:
                if prompt:
                    print(f"{C.CYAN}> {prompt}{C.RESET}")
                    rc = await _run_chat_turn(
                        client=client,
                        url=url,
                        headers=headers,
                        model=settings.model,
                        settings=settings,
                        mcp_client=mcp_client,
                        messages=messages,
                        user_text=prompt,
                    )
                    if rc != 0:
                        if rc == 130:
                            prompt = ""
                        else:
                            return rc

                while True:
                    try:
                        line = input(f"{C.CYAN}> {C.RESET}").strip()
                    except EOFError:
                        print()
                        return 0
                    except KeyboardInterrupt:
                        print()
                        continue

                    if not line:
                        continue
                    if line in {"/", "/help"}:
                        _print_repl_commands()
                        continue
                    if line in {"/exit", "/quit"}:
                        return 0
                    if line == "/history":
                        _print_history(messages)
                        continue
                    if line == "/reset":
                        messages = []
                        if settings.system_prompt:
                            messages.append({"role": "system", "content": settings.system_prompt})
                        print(f"{C.YELLOW}history reset{C.RESET}")
                        continue
                    if line == "/models":
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
                                f"{C.DIM}mcp={mcp_client.endpoint or '<disconnected>'} "
                                f"tools={len(mcp_client.list_tool_names())}{C.RESET}"
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
                                    f"{C.GREEN}{CHECK}{C.RESET} mcp connected: {endpoint} "
                                    f"({len(mcp_client.list_tool_names())} tools)"
                                )
                            except Exception as exc:
                                error(f"mcp connect failed: {exc}")
                            continue
                        if sub == "disconnect":
                            await mcp_client.disconnect()
                            print(f"{C.GREEN}{CHECK}{C.RESET} mcp disconnected")
                            continue
                        if sub == "tools":
                            names = mcp_client.list_tool_names()
                            if not names:
                                print(f"{C.DIM}no mcp tools available{C.RESET}")
                            else:
                                print(f"{C.BLUE}mcp tools:{C.RESET} {', '.join(names)}")
                            continue
                        warn("usage: /mcp <connect|disconnect|status|tools>")
                        continue
                    if line.startswith("/"):
                        matches = [cmd for cmd in REPL_COMMANDS if cmd.startswith(line)]
                        if matches:
                            _print_repl_commands(line)
                        else:
                            warn(f"unknown command: {line}")
                            _print_repl_commands()
                        continue

                    rc = await _run_chat_turn(
                        client=client,
                        url=url,
                        headers=headers,
                        model=settings.model,
                        settings=settings,
                        mcp_client=mcp_client,
                        messages=messages,
                        user_text=line,
                    )
                    if rc != 0:
                        if rc == 130:
                            continue
                        return rc
            finally:
                if cleanup_repl:
                    cleanup_repl()
                await mcp_client.disconnect()
        return 0
    except Exception as e:
        try:
            spinner.fail(f"Chat request failed: {e}")  # type: ignore[name-defined]
        except Exception:
            error(f"Chat request failed: {e}")
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


def _normalize_finish_reason(fr: str | None) -> str | None:
    if fr is None:
        return None
    s = str(fr).strip().lower()
    if s in {"stop", "finish_stop"}:
        return "stop"
    if s in {"length", "finish_length"}:
        return "length"
    if s in {"tool_calls", "toolcalls", "finish_toolcalls"}:
        return "tool_calls"
    if s in {"content_filter"}:
        return "content_filter"
    return "stop"


def _normalize_usage_dict(usage: dict | None) -> dict | None:
    if not isinstance(usage, dict):
        return usage
    if {"prompt_tokens", "completion_tokens", "total_tokens"}.issubset(set(usage.keys())):
        return usage
    tokens = usage.get("tokens")
    if isinstance(tokens, dict):
        prompt = int(tokens.get("prompt", 0) or 0)
        completion = int(tokens.get("completion", 0) or 0)
        out = dict(usage)
        out["prompt_tokens"] = prompt
        out["completion_tokens"] = completion
        out["total_tokens"] = prompt + completion
        return out
    return usage


def _flatten_content(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text", "")))
        return "".join(parts)
    return str(content)


def _extract_tool_calls_and_clean(text: str) -> tuple[list[dict], str]:
    calls: list[dict] = []
    for m in TOOL_TAG_PATTERN.findall(text):
        try:
            obj = json.loads(m.strip())
            if isinstance(obj, dict):
                calls.append(obj)
        except Exception:
            continue
    cleaned = TOOL_TAG_PATTERN.sub("", text).strip()
    return calls, cleaned


def _tool_prompt(tools_spec: list[dict]) -> str:
    desc_lines: list[str] = []
    for t in tools_spec:
        if not isinstance(t, dict) or t.get("type") != "function":
            continue
        fn = t.get("function", {})
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            continue
        description = str(fn.get("description") or "")
        params = fn.get("parameters") if isinstance(fn.get("parameters"), dict) else {"type": "object"}
        desc_lines.append(f"{name}: {description}\nArg Schema: {json.dumps(params, indent=2)}")
    if not desc_lines:
        return ""
    open_tag, close_tag = TOOL_TAGS
    return (
        "You have access to the following tools:\n"
        + "\n".join(desc_lines)
        + "\nWhen you decide to use a tool, respond with a JSON object enclosed by "
        + f"{open_tag} and {close_tag} tags in this format:\n"
        + f"{open_tag}\n"
        + '{\n  "tool": "<tool_name>",\n  "args": {<tool_arguments_as_json_object>}\n}\n'
        + f"{close_tag}\n"
        + "Only use tools listed above, and ensure your JSON is valid."
    )


def _serialize_tool_calls(tool_calls: list[dict]) -> str:
    blocks: list[str] = []
    open_tag, close_tag = TOOL_TAGS
    for tc in tool_calls:
        if not isinstance(tc, dict) or tc.get("type") != "function":
            continue
        fn = tc.get("function", {})
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            continue
        args_raw = fn.get("arguments")
        args = {}
        if isinstance(args_raw, str):
            try:
                maybe = json.loads(args_raw)
                if isinstance(maybe, dict):
                    args = maybe
            except Exception:
                args = {"_raw": args_raw}
        elif isinstance(args_raw, dict):
            args = args_raw
        blocks.append(f"{open_tag}\n{json.dumps({'tool': name, 'args': args})}\n{close_tag}")
    return "\n".join(blocks)


def _massage_messages_for_tools(messages: list[dict], tools_spec: list[dict], tool_choice: object) -> list[dict]:
    out: list[dict] = []
    prompt = _tool_prompt(tools_spec) if tool_choice != "none" else ""
    injected = False

    tool_name_by_id: dict[str, str] = {}
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            for tc in msg.get("tool_calls", []) or []:
                if isinstance(tc, dict):
                    tc_id = tc.get("id")
                    fn = tc.get("function", {})
                    if isinstance(tc_id, str) and isinstance(fn, dict) and isinstance(fn.get("name"), str):
                        tool_name_by_id[tc_id] = fn["name"]

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = _flatten_content(msg.get("content"))

        if role == "assistant" and isinstance(msg.get("tool_calls"), list):
            serialized = _serialize_tool_calls(msg.get("tool_calls") or [])
            if serialized:
                content = (content + "\n" + serialized).strip()

        if role == "tool":
            tool_name = msg.get("name")
            if not isinstance(tool_name, str) or not tool_name:
                tcid = msg.get("tool_call_id")
                if isinstance(tcid, str):
                    tool_name = tool_name_by_id.get(tcid, "")
            content = f'<tool_result> "tool" : "{tool_name or ""}" "output": "{content}" </tool_result>'

        if role == "system" and prompt and not injected:
            content = (content + "\n\n" + prompt).strip()
            injected = True

        out.append({"role": role, "content": content})

    if prompt and not injected:
        out.insert(0, {"role": "system", "content": prompt})
    return out


class _ToolTagStreamFilter:
    def __init__(self):
        self.buf = ""

    def feed(self, text: str) -> str:
        if not text:
            return ""
        s = self.buf + text
        self.buf = ""
        out: list[str] = []
        open_tag, close_tag = TOOL_TAGS
        while s:
            start = s.find(open_tag)
            if start == -1:
                keep = len(open_tag) - 1
                if len(s) > keep:
                    out.append(s[:-keep] if keep > 0 else s)
                    self.buf = s[-keep:] if keep > 0 else ""
                else:
                    self.buf = s
                break
            if start > 0:
                out.append(s[:start])
            s = s[start:]
            end = s.find(close_tag)
            if end == -1:
                self.buf = s
                break
            s = s[end + len(close_tag):]
        return "".join(out)

    def finalize(self) -> str:
        if not self.buf:
            return ""
        open_tag, _ = TOOL_TAGS
        if open_tag in self.buf:
            self.buf = ""
            return ""
        tail = self.buf
        self.buf = ""
        return tail


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
                if isinstance(body.get("tools"), list):
                    messages = body.get("messages", [])
                    if isinstance(messages, list):
                        body["messages"] = _massage_messages_for_tools(
                            messages=messages,
                            tools_spec=body.get("tools") or [],
                            tool_choice=body.get("tool_choice"),
                        )
                # Let proxy map tool tags back to OpenAI tool_calls.
                body.pop("tools", None)
                body.pop("tool_choice", None)

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
                            tool_filter = _ToolTagStreamFilter()
                            acc_text_parts: list[str] = []
                            seen_finish_reason: str | None = None
                            stream_id = None
                            created = None
                            model_name = None
                            for raw_line in resp.iter_lines():
                                line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", errors="replace")
                                if not line:
                                    self.wfile.write(b"\n")
                                    self.wfile.flush()
                                    continue
                                if line.startswith("data:"):
                                    payload = line[5:].strip()
                                    if payload == "[DONE]":
                                        clean_tail = tool_filter.finalize()
                                        if clean_tail:
                                            chunk = {
                                                "choices": [{"index": 0, "delta": {"content": clean_tail}, "finish_reason": None}]
                                            }
                                            if stream_id is not None:
                                                chunk["id"] = stream_id
                                            if created is not None:
                                                chunk["created"] = created
                                            if model_name is not None:
                                                chunk["model"] = model_name
                                            out = f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n"
                                            self.wfile.write(out.encode("utf-8"))

                                        if acc_text_parts:
                                            tool_calls, _clean = _extract_tool_calls_and_clean("".join(acc_text_parts))
                                            if tool_calls:
                                                tc_list = []
                                                for i, tc in enumerate(tool_calls):
                                                    name = str(tc.get("tool", ""))
                                                    args = tc.get("args", {})
                                                    if not isinstance(args, dict):
                                                        args = {"_raw": str(args)}
                                                    tc_list.append(
                                                        {
                                                            "id": f"call_{i+1}",
                                                            "type": "function",
                                                            "index": i,
                                                            "function": {"name": name, "arguments": json.dumps(args, separators=(',', ':'))},
                                                        }
                                                    )
                                                tc_chunk = {
                                                    "choices": [{"index": 0, "delta": {"tool_calls": tc_list}, "finish_reason": None}]
                                                }
                                                if stream_id is not None:
                                                    tc_chunk["id"] = stream_id
                                                if created is not None:
                                                    tc_chunk["created"] = created
                                                if model_name is not None:
                                                    tc_chunk["model"] = model_name
                                                out = f"data: {json.dumps(tc_chunk, separators=(',', ':'))}\n\n"
                                                self.wfile.write(out.encode("utf-8"))
                                                seen_finish_reason = "tool_calls"

                                        if seen_finish_reason is None:
                                            fin = {
                                                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                                            }
                                            if stream_id is not None:
                                                fin["id"] = stream_id
                                            if created is not None:
                                                fin["created"] = created
                                            if model_name is not None:
                                                fin["model"] = model_name
                                            out = f"data: {json.dumps(fin, separators=(',', ':'))}\n\n"
                                            self.wfile.write(out.encode("utf-8"))

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
                                        if stream_id is None and isinstance(evt, dict):
                                            stream_id = evt.get("id")
                                            created = evt.get("created")
                                            model_name = evt.get("model")
                                        if include_think_tags:
                                            evt = _inject_reasoning_into_chunk(evt, state)
                                        else:
                                            # OpenAI-style proxy field for reasoning deltas.
                                            choices = evt.get("choices")
                                            if isinstance(choices, list) and choices:
                                                c0 = choices[0]
                                                if isinstance(c0, dict):
                                                    delta = c0.get("delta")
                                                    if isinstance(delta, dict) and isinstance(delta.get("reasoning"), str):
                                                        delta["reasoning_content"] = delta.pop("reasoning")
                                        choices = evt.get("choices")
                                        if isinstance(choices, list) and choices:
                                            c0 = choices[0]
                                            if isinstance(c0, dict):
                                                fr = c0.get("finish_reason")
                                                mapped_fr = _normalize_finish_reason(fr) if fr is not None else None
                                                if fr is not None:
                                                    c0["finish_reason"] = mapped_fr
                                                    seen_finish_reason = mapped_fr
                                                delta = c0.get("delta")
                                                if isinstance(delta, dict):
                                                    content = delta.get("content")
                                                    if isinstance(content, str) and content:
                                                        acc_text_parts.append(content)
                                                        filtered = tool_filter.feed(content)
                                                        if filtered != content:
                                                            if filtered:
                                                                delta["content"] = filtered
                                                            else:
                                                                delta.pop("content", None)
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
                                choices = parsed.get("choices")
                                if isinstance(choices, list) and choices:
                                    c0 = choices[0]
                                    if isinstance(c0, dict):
                                        msg = c0.get("message")
                                        if isinstance(msg, dict):
                                            msg_content = msg.get("content")
                                            if isinstance(msg_content, str):
                                                tool_calls, cleaned = _extract_tool_calls_and_clean(msg_content)
                                                if tool_calls:
                                                    tc_list = []
                                                    for i, tc in enumerate(tool_calls):
                                                        name = str(tc.get("tool", ""))
                                                        args = tc.get("args", {})
                                                        if not isinstance(args, dict):
                                                            args = {"_raw": str(args)}
                                                        tc_list.append(
                                                            {
                                                                "id": f"call_{i+1}",
                                                                "type": "function",
                                                                "function": {"name": name, "arguments": json.dumps(args, separators=(',', ':'))},
                                                            }
                                                        )
                                                    msg["tool_calls"] = tc_list
                                                    msg["content"] = cleaned if cleaned else None
                                                    c0["finish_reason"] = "tool_calls"
                                        fr = c0.get("finish_reason")
                                        c0["finish_reason"] = _normalize_finish_reason(fr) if fr is not None else None
                                usage = parsed.get("usage")
                                if isinstance(usage, dict):
                                    parsed["usage"] = _normalize_usage_dict(usage)
                                content = json.dumps(parsed).encode("utf-8")
                            except Exception:
                                pass
                        elif mapped == "/if2/v1/chat/completions" and "application/json" in resp.headers.get("content-type", ""):
                            try:
                                parsed = json.loads(content.decode("utf-8"))
                                choices = parsed.get("choices")
                                if isinstance(choices, list) and choices:
                                    c0 = choices[0]
                                    if isinstance(c0, dict):
                                        msg = c0.get("message")
                                        if isinstance(msg, dict):
                                            msg_content = msg.get("content")
                                            if isinstance(msg_content, str):
                                                tool_calls, cleaned = _extract_tool_calls_and_clean(msg_content)
                                                if tool_calls:
                                                    tc_list = []
                                                    for i, tc in enumerate(tool_calls):
                                                        name = str(tc.get("tool", ""))
                                                        args = tc.get("args", {})
                                                        if not isinstance(args, dict):
                                                            args = {"_raw": str(args)}
                                                        tc_list.append(
                                                            {
                                                                "id": f"call_{i+1}",
                                                                "type": "function",
                                                                "function": {"name": name, "arguments": json.dumps(args, separators=(',', ':'))},
                                                            }
                                                        )
                                                    msg["tool_calls"] = tc_list
                                                    msg["content"] = cleaned if cleaned else None
                                                    c0["finish_reason"] = "tool_calls"
                                        fr = c0.get("finish_reason")
                                        c0["finish_reason"] = _normalize_finish_reason(fr) if fr is not None else None
                                usage = parsed.get("usage")
                                if isinstance(usage, dict):
                                    parsed["usage"] = _normalize_usage_dict(usage)
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
    if sys.stdout.isatty():
        intro = MushroomPulse("truffile", interval=0.08)
        intro.start()
        time.sleep(0.65)
        intro.stop()
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
    print(f"  {C.BLUE}models{C.RESET}                    List models on your Truffle")
    print(f"  {C.BLUE}chat{C.RESET}                     Chat on your Truffle (REPL by default)")
    print(f"  {C.BLUE}proxy{C.RESET}                    Run OpenAI-compatible proxy")
    print()
    print(f"{C.BOLD}Examples:{C.RESET}")
    print(f"  {C.DIM}truffile scan{C.RESET}                {C.DIM}# find devices on network{C.RESET}")
    print(f"  {C.DIM}truffile connect truffle-6272{C.RESET}")
    print(f"  {C.DIM}truffile deploy ./my-app{C.RESET}")
    print(f"  {C.DIM}truffile deploy --dry-run ./my-app{C.RESET}")
    print(f"  {C.DIM}truffile deploy{C.RESET}              {C.DIM}# uses current directory{C.RESET}")
    print(f"  {C.DIM}truffile validate ./my-app{C.RESET}")
    print(f"  {C.DIM}truffile list apps{C.RESET}")
    print(f"  {C.DIM}truffile models{C.RESET}              {C.DIM}# show models on your Truffle{C.RESET}")
    print(f"  {C.DIM}truffile chat{C.RESET}               {C.DIM}# open interactive REPL chat{C.RESET}")
    print(f"  {C.DIM}# in chat: /help, /config, /reasoning on|off, /mcp connect <url>{C.RESET}")
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
