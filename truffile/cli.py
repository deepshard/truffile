import argparse
import asyncio
import ast
import signal
import socket
import sys
import threading
import time
from pathlib import Path

import yaml

from truffile.storage import StorageService
from truffile.client import TruffleClient, resolve_mdns, NewSessionStatus

import grpc
from truffle.infer.infer_pb2_grpc import InferenceServiceStub
from truffle.infer.model_pb2 import GetModelListRequest, Model


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


def check_python_syntax(file_path: Path) -> tuple[bool, str]:
    try:
        with open(file_path) as f:
            source = f.read()
        ast.parse(source)
        return True, ""
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"


def validate_app_dir(app_dir: Path) -> tuple[bool, dict | None, str | None, list[str]]:
    """Validate app directory and return (valid, config, app_type, warnings)."""
    warnings = []
    
    truffile = app_dir / "truffile.yaml"
    if not truffile.exists():
        error(f"No truffile.yaml found in {app_dir}")
        return False, None, None, warnings
    
    try:
        with open(truffile) as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        error(f"Invalid truffile.yaml: {e}")
        return False, None, None, warnings
    
    meta = config.get("metadata", {})
    if not meta.get("name"):
        error("metadata.name is required in truffile.yaml")
        return False, None, None, warnings
    
    cfg_type = meta.get("type", "").lower()
    if cfg_type in ("background", "ambient"):
        app_type = "ambient"
    elif cfg_type in ("foreground", "focus"):
        app_type = "focus"
    else:
        app_type = "focus"
        warnings.append(f"No type specified in truffile.yaml, defaulting to focus")
    
    icon_file = meta.get("icon_file")
    if icon_file:
        icon_path = app_dir / icon_file
        if not icon_path.exists():
            warnings.append(f"Icon file not found: {icon_file}")
    else:
        warnings.append("No icon specified in truffile.yaml")
    
    # Check files - either in steps or top-level files:
    files_to_check = []
    for step in config.get("steps", []):
        if step.get("type") == "files":
            files_to_check.extend(step.get("files", []))
    # Also check top-level files: (simplified format)
    files_to_check.extend(config.get("files", []))
    
    for f in files_to_check:
        src = app_dir / f["source"]
        if not src.exists():
            error(f"Source file not found: {src}")
            return False, None, None, warnings
        if src.suffix == ".py":
            ok, err = check_python_syntax(src)
            if not ok:
                error(f"Syntax error in {src.name}: {err}")
                return False, None, None, warnings
    
    return True, config, app_type, warnings


async def _do_deploy(client: TruffleClient, config: dict, app_dir: Path, app_type: str, device: str, interactive: bool = False) -> int:
    meta = config["metadata"]
    name = meta["name"]
    description = meta.get("description", "")
    process = meta.get("process", {})
    cmd_list = process.get("cmd", ["python", "app.py"])
    cwd = process.get("working_directory", "/")
    env_dict = process.get("environment", {})
    env = [f"{k}={v}" for k, v in env_dict.items()]
    icon_file = meta.get("icon_file")
    icon_path = (app_dir / icon_file) if icon_file and (app_dir / icon_file).exists() else None

    spinner = Spinner(f"Connecting to {device}")
    spinner.start()
    await client.connect()
    spinner.stop(success=True)
    
    spinner = Spinner("Starting build session")
    spinner.start()
    await client.start_build()
    await asyncio.sleep(5)
    spinner.stop(success=True)
    print(f"  {C.DIM}Session: {client.app_uuid}{C.RESET}")
    
    # Always upload files first
    files_to_upload = []
    for step in config.get("steps", []):
        if step.get("type") == "files":
            files_to_upload.extend(step.get("files", []))
    files_to_upload.extend(config.get("files", []))
    
    for f in files_to_upload:
        src = app_dir / f["source"]
        dest = f["destination"]
        spinner = Spinner(f"Uploading {src.name} {ARROW} {dest}")
        spinner.start()
        result = await client.upload(src, dest)
        spinner.stop(success=True)
        print(f"  {C.DIM}{result.bytes} bytes, sha256={result.sha256[:12]}...{C.RESET}")
    
    # always run bash commands
    bash_commands = []
    for step in config.get("steps", []):
        if step.get("type") == "bash":
            bash_commands.append((step.get("name", "bash"), step["run"]))
    if config.get("run"):
        bash_commands.append(("Install dependencies", config["run"]))
    
    for step_name, run_cmd in bash_commands:
        info(f"Running: {step_name}")
        log = ScrollingLog(height=6, prefix="  ")
        exit_code = 0
        async for ev, data in client.exec_stream(run_cmd, cwd=cwd):
            if ev == "log":
                try:
                    import json
                    obj = json.loads(data)
                    line = obj.get("line", "")
                except Exception:
                    line = data
                log.add(line)
            elif ev == "exit":
                try:
                    import json
                    exit_code = int(json.loads(data).get("code", 0))
                except (ValueError, KeyError):
                    pass
        log.finish()
        if exit_code != 0:
            error(f"Step '{step_name}' failed with exit code {exit_code}")
            raise RuntimeError(f"Step '{step_name}' failed with exit code {exit_code}")
    
    if interactive:
        # interactive mode: open shell after setup for testing/debugging
        print()
        info("Opening interactive shell (exit with Ctrl+D or 'exit' to finish deploy)")
        ws_url = str(client.http_base or "").replace("http://", "ws://").replace("https://", "wss://") + "/term"
        await _interactive_shell(ws_url)
        print()
    spinner = Spinner(f"Finishing as {app_type} app")
    spinner.start()
    
    cmd = cmd_list[0] if cmd_list[0].startswith("/") else f"/usr/bin/{cmd_list[0]}"
    
    if app_type == "focus":
        await client.finish_foreground(
            name=name,
            cmd=cmd,
            args=cmd_list[1:],
            cwd=cwd,
            env=env,
            description=description,
            icon=icon_path,
        )
    else:
        default_schedule = meta.get("default_schedule")
        await client.finish_background(
            name=name,
            cmd=cmd,
            args=cmd_list[1:],
            cwd=cwd,
            env=env,
            description=description,
            icon=icon_path,
            default_schedule=default_schedule,
        )
    
    spinner.stop(success=True)
    print()
    success(f"Deployed: {C.BOLD}{name}{C.RESET} ({app_type})")
    return 0


async def cmd_deploy(args, storage: StorageService) -> int:
    app_path = args.path if args.path else "."
    app_dir = Path(app_path).resolve()
    interactive = args.interactive
    if not app_dir.exists() or not app_dir.is_dir():
        error(f"{app_dir} is not a valid directory")
        return 1
    
    info(f"Validating app in {app_dir.name}")
    valid, config, app_type, warnings = validate_app_dir(app_dir)
    if not valid or not app_type:
        return 1
    
    for w in warnings:
        warn(w)
    
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
        deploy_task = asyncio.create_task(_do_deploy(client, config, app_dir, app_type, device, interactive))
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
        foreground, background = await client.get_all_apps()
        spinner.stop(success=True)
        
        if not foreground and not background:
            print(f"  {C.DIM}No apps installed{C.RESET}")
            return 0
        
        print()
        if foreground:
            print(f"{C.BOLD}Focus Apps{C.RESET}")
            for app in foreground:
                print(f"  {C.CYAN}{DOT}{C.RESET} {app.metadata.name}")
                setattr(app.metadata, "description", getattr(app.metadata, "description", ""))
                if hasattr(app.metadata, "description") and app.metadata.description:
                    desc = app.metadata.description.strip().split('\n')[0][:55]
                    print(f"    {C.DIM}{desc}{C.RESET}")
        
        if background:
            if foreground:
                print()
            print(f"{C.BOLD}Ambient Apps{C.RESET}")
            for app in background:
                schedule = ""
                if app.runtime_policy.HasField("interval"):
                    secs = app.runtime_policy.interval.duration.seconds
                    if secs >= 3600:
                        schedule = f"every {secs // 3600}h"
                    elif secs >= 60:
                        schedule = f"every {secs // 60}m"
                    else:
                        schedule = f"every {secs}s"
                elif app.runtime_policy.HasField("always"):
                    schedule = "always"
                print(f"  {C.CYAN}{DOT}{C.RESET} {app.metadata.name} {C.DIM}({schedule}){C.RESET}")
                setattr(app.metadata, "description", getattr(app.metadata, "description", ""))
                if hasattr(app.metadata, "description") and app.metadata.description:
                    desc = app.metadata.description.strip().split('\n')[0][:55]
                    print(f"    {C.DIM}{desc}{C.RESET}")
        
        print()
        print(f"{C.DIM}Total: {len(foreground)} focus, {len(background)} ambient{C.RESET}")
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
    """List models on the connected device."""
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
        channel = grpc.insecure_channel(f"{ip}:80")
        stub = InferenceServiceStub(channel)
        model_list = stub.GetModelList(GetModelListRequest(use_filter=False))
        spinner.stop(success=True)
    except Exception as e:
        spinner.fail(f"Failed to get models: {e}")
        return 1
    
    loaded = [m for m in model_list.models if m.state == Model.MODEL_STATE_LOADED]
    available = [m for m in model_list.models if m.state == Model.MODEL_STATE_AVAILABLE]
    
    print()
    print(f"{MUSHROOM} {C.BOLD}Models on {device}{C.RESET}")
    print()
    
    if loaded:
        for m in loaded:
            reasoner = f" {C.MAGENTA}reasoner{C.RESET}" if m.config.info.has_chain_of_thought else ""
            print(f"  {C.GREEN}{CHECK}{C.RESET} {m.name}{reasoner}")
            print(f"    {C.DIM}id: {m.uuid}{C.RESET}")
    
    if available:
        for m in available:
            print(f"  {C.DIM}○ {m.name} (not loaded){C.RESET}")
    
    if not loaded and not available:
        print(f"  {C.DIM}No models found{C.RESET}")
    
    print()
    total_mb = model_list.total_memory // (1024 * 1024) if model_list.total_memory else 0
    used_mb = model_list.used_memory // (1024 * 1024) if model_list.used_memory else 0
    print(f"{C.DIM}Memory: {used_mb}MB / {total_mb}MB{C.RESET}")
    
    return 0


def cmd_proxy(args, storage: StorageService) -> int:
    """Start the OpenAI-compatible proxy."""
    device = args.device if hasattr(args, 'device') and args.device else storage.state.last_used_device
    if not device:
        error("No device specified or connected")
        print(f"  {C.DIM}Run: truffile connect <device>{C.RESET}")
        print(f"  {C.DIM}Or:  truffile proxy --device <device>{C.RESET}")
        return 1
    
    port = args.port if hasattr(args, 'port') else 8080
    host = args.host if hasattr(args, 'host') else "127.0.0.1"
    debug = args.debug if hasattr(args, 'debug') else False
    
    spinner = None
    
    try:
        print(f"{MUSHROOM} {C.BOLD}Starting OpenAI proxy{C.RESET}")
        print()
        
        spinner = Spinner(f"Resolving {device}.local")
        spinner.start()
        
        hostname = f"{device}.local"
        ip = socket.gethostbyname(hostname)
        spinner.stop(success=True)
        
        grpc_address = f"{ip}:80"
        
        spinner = Spinner("Connecting to inference service")
        spinner.start()
        
        from truffile.infer.proxy import OpenAIProxy, OpenAIProxyHandler
        from http.server import ThreadingHTTPServer
        
        proxy = OpenAIProxy(grpc_address, include_debug=debug)
        
        channel = grpc.insecure_channel(grpc_address)
        stub = InferenceServiceStub(channel)
        model_list = stub.GetModelList(GetModelListRequest(use_filter=False))
        loaded = [m for m in model_list.models if m.state == Model.MODEL_STATE_LOADED]
        spinner.stop(success=True)
        spinner = None
        
        print(f"  {C.DIM}Device: {device} ({ip}){C.RESET}")
        print(f"  {C.DIM}Models: {len(loaded)} loaded{C.RESET}")
        
        print()
        print(f"{C.GREEN}{CHECK}{C.RESET} Proxy running at {C.BOLD}http://{host}:{port}/v1{C.RESET}")
        print()
        print(f"  {C.DIM}Use with OpenAI SDK:{C.RESET}")
        print(f"    {C.CYAN}from openai import OpenAI{C.RESET}")
        print(f"    {C.CYAN}client = OpenAI(base_url=\"http://{host}:{port}/v1\", api_key=\"x\"){C.RESET}")
        print()
        print(f"  {C.DIM}Or set environment variables:{C.RESET}")
        print(f"    {C.CYAN}export OPENAI_BASE_URL=http://{host}:{port}/v1{C.RESET}")
        print(f"    {C.CYAN}export OPENAI_API_KEY=anything{C.RESET}")
        print()
        print(f"  {C.DIM}Press Ctrl+C to stop{C.RESET}")
        print()
        
        class _Server(ThreadingHTTPServer):
            def __init__(self, server_address, handler_cls):
                super().__init__(server_address, handler_cls)
                self.proxy = proxy
        
        server = _Server((host, port), OpenAIProxyHandler)
        server.serve_forever()
        
    except KeyboardInterrupt:
        if spinner:
            spinner.running = False
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
        print(f"{C.RED}{CROSS} Cancelled{C.RESET}")
        return 130
    except socket.gaierror:
        if spinner:
            spinner.fail(f"Could not resolve {device}.local")
        else:
            error(f"Could not resolve {device}.local")
        print(f"  {C.DIM}Try: ping {device}.local{C.RESET}")
        return 1
    except OSError as e:
        if spinner:
            spinner.fail(str(e))
        else:
            error(f"Could not start server: {e}")
        print(f"  {C.DIM}Port {port} may already be in use{C.RESET}")
        return 1
    except Exception as e:
        if spinner:
            spinner.fail(str(e))
        else:
            error(str(e))
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
    print(f"  {C.BLUE}list{C.RESET} <apps|devices>      List installed apps or devices")
    print(f"  {C.BLUE}models{C.RESET}                    List AI models on connected device")
    print(f"  {C.BLUE}proxy{C.RESET}                     Start OpenAI-compatible inference proxy")
    print()
    print(f"{C.BOLD}Examples:{C.RESET}")
    print(f"  {C.DIM}truffile scan{C.RESET}                {C.DIM}# find devices on network{C.RESET}")
    print(f"  {C.DIM}truffile connect truffle-6272{C.RESET}")
    print(f"  {C.DIM}truffile deploy ./my-app{C.RESET}")
    print(f"  {C.DIM}truffile deploy{C.RESET}              {C.DIM}# uses current directory{C.RESET}")
    print(f"  {C.DIM}truffile list apps{C.RESET}")
    print(f"  {C.DIM}truffile models{C.RESET}              {C.DIM}# show loaded models{C.RESET}")
    print(f"  {C.DIM}truffile proxy{C.RESET}               {C.DIM}# start proxy on :8080{C.RESET}")
    print(f"  {C.DIM}truffile proxy --port 9000{C.RESET}")
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

    p_list = subparsers.add_parser("list", add_help=False)
    p_list.add_argument("what", choices=["apps", "devices"], nargs="?")

    p_models = subparsers.add_parser("models", add_help=False)

    p_proxy = subparsers.add_parser("proxy", add_help=False)
    p_proxy.add_argument("--device", "-d", help="Device name (defaults to last connected)")
    p_proxy.add_argument("--port", "-p", type=int, default=8080, help="Port to listen on")
    p_proxy.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    p_proxy.add_argument("--debug", action="store_true", help="Include reasoning in responses")

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
    elif args.command == "deploy":
        return run_async(cmd_deploy(args, storage))
    elif args.command == "list":
        return cmd_list(args, storage)
    elif args.command == "models":
        return run_async(cmd_models(storage))
    elif args.command == "proxy":
        return cmd_proxy(args, storage)

    return 0


if __name__ == "__main__":
    sys.exit(main())
