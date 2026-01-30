import argparse
import asyncio
import ast
import signal
import sys
from pathlib import Path

import yaml

from genesis.storage import StorageService
from genesis.client import TruffleClient, resolve_mdns, NewSessionStatus


async def cmd_connect(args, storage: StorageService) -> int:
    device_name = args.device
    
    print(f"Connecting to {device_name}...")
    
    hostname = f"{device_name}.local"
    try:
        ip = await resolve_mdns(hostname)
    except RuntimeError as e:
        print(f"Could not find device: {e}")
        print()
        print("Make sure:")
        print(f"  - {device_name} is powered on")
        print("  - Device is connected to WiFi")
        print("  - Your computer is on the same network")
        return 1
    
    address = f"{ip}:80"
    existing_token = storage.get_token(device_name)
    
    if existing_token:
        print("Validating existing token...")
        client = TruffleClient(address, existing_token)
        try:
            await client.connect()
            if await client.check_auth():
                storage.set_last_used(device_name)
                print(f"Already connected to {device_name}")
                await client.close()
                return 0
            print("Token invalid, re-authenticating...")
        except Exception:
            pass
        finally:
            await client.close()
    
    print()
    print("Make sure you have:")
    print("  - Onboarded with the Truffle app")
    print("  - Your User ID from the recovery codes")
    print()
    
    user_id = input("Enter your User ID: ").strip()
    if not user_id:
        print("User ID is required")
        return 1
    
    client = TruffleClient(address, token="")
    try:
        await client.connect()
    except Exception as e:
        print(f"Failed to connect to device: {e}")
        return 1
    
    print()
    print("Requesting authorization...")
    print("Please approve the connection request on your Truffle device")
    print("(waiting for approval...)")
    
    try:
        status, token = await client.register_new_session(user_id)
    except Exception as e:
        print(f"Failed to register: {e}")
        await client.close()
        return 1
    
    await client.close()
    
    if status.error == NewSessionStatus.NEW_SESSION_SUCCESS and token:
        storage.set_token(device_name, token)
        storage.set_last_used(device_name)
        print()
        print(f"Connected to {device_name}")
        return 0
    elif status.error == NewSessionStatus.NEW_SESSION_TIMEOUT:
        print()
        print("Approval timed out. Please try again.")
        return 1
    elif status.error == NewSessionStatus.NEW_SESSION_REJECTED:
        print()
        print("Request was rejected.")
        return 1
    else:
        print()
        print(f"Failed to authenticate: {status.error}")
        return 1


def cmd_disconnect(args, storage: StorageService) -> int:
    target = args.target
    if target == "all":
        storage.clear_all()
        print("All device credentials cleared")
    else:
        if storage.remove_device(target):
            print(f"Disconnected from {target} (credentials cleared)")
        else:
            print(f"No credentials found for {target}")
    return 0


def check_python_syntax(file_path: Path) -> tuple[bool, str]:
    try:
        with open(file_path) as f:
            source = f.read()
        ast.parse(source)
        return True, ""
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"


def validate_app_dir(app_dir: Path, app_type: str) -> tuple[bool, dict | None, list[str]]:
    warnings = []
    
    truffile = app_dir / "truffile.yaml"
    if not truffile.exists():
        print(f"Error: No truffile.yaml found in {app_dir}")
        return False, None, warnings
    
    try:
        with open(truffile) as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"Error: Invalid truffile.yaml: {e}")
        return False, None, warnings
    
    meta = config.get("metadata", {})
    if not meta.get("name"):
        print("Error: metadata.name is required in truffile.yaml")
        return False, None, warnings
    
    cfg_type = meta.get("type", "")
    if app_type == "ambient" and cfg_type not in ("background", "ambient", ""):
        print(f"Error: This is a {cfg_type} app, not an ambient app")
        print(f"  Use: genesis deploy focus {app_dir.name}")
        return False, None, warnings
    elif app_type == "focus" and cfg_type not in ("foreground", "focus", ""):
        print(f"Error: This is a {cfg_type} app, not a focus app")
        print(f"  Use: genesis deploy ambient {app_dir.name}")
        return False, None, warnings
    
    icon_file = meta.get("icon_file")
    if icon_file:
        icon_path = app_dir / icon_file
        if not icon_path.exists():
            warnings.append(f"Icon file not found: {icon_file}")
    else:
        warnings.append("No icon specified in truffile.yaml")
    
    for step in config.get("steps", []):
        if step.get("type") == "files":
            for f in step.get("files", []):
                src = app_dir / f["source"]
                if not src.exists():
                    print(f"Error: Source file not found: {src}")
                    return False, None, warnings
                if src.suffix == ".py":
                    ok, err = check_python_syntax(src)
                    if not ok:
                        print(f"Error: Syntax error in {src.name}: {err}")
                        return False, None, warnings
    
    return True, config, warnings


async def _do_deploy(client: TruffleClient, config: dict, app_dir: Path, app_type: str, device: str) -> int:
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

    print(f"Connecting to {device}...")
    await client.connect()
    
    print("Starting build session...")
    await client.start_build()
    print(f"  Session: {client.app_uuid}")
    
    for step in config.get("steps", []):
        if step.get("type") == "files":
            for f in step.get("files", []):
                src = app_dir / f["source"]
                dest = f["destination"]
                print(f"Uploading {src.name} -> {dest}")
                result = await client.upload(src, dest)
                print(f"  {result.bytes} bytes, sha256={result.sha256[:12]}...")
                
        elif step.get("type") == "bash":
            step_name = step.get("name", "bash")
            print(f"Running: {step_name}")
            async for ev, data in client.exec_stream(step["run"], cwd=cwd):
                if ev == "log":
                    try:
                        import json
                        obj = json.loads(data)
                        line = obj.get("line", "")
                    except Exception:
                        line = data
                    print(f"  {line}")
                elif ev == "exit":
                    try:
                        import json
                        code = int(json.loads(data).get("code", 0))
                        if code != 0:
                            print(f"  Exit code: {code}")
                            raise RuntimeError(f"Step '{step_name}' failed with exit code {code}")
                    except (ValueError, KeyError):
                        pass
    
    print(f"Finishing as {app_type} app...")
    
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
        schedule_cfg = meta.get("default_schedule", {})
        schedule_type = schedule_cfg.get("type", "interval")
        interval_seconds = 60
        
        if schedule_type == "interval":
            interval_cfg = schedule_cfg.get("interval", {})
            duration_str = interval_cfg.get("duration", "1m")
            if duration_str.endswith("m"):
                interval_seconds = int(duration_str[:-1]) * 60
            elif duration_str.endswith("h"):
                interval_seconds = int(duration_str[:-1]) * 3600
            elif duration_str.endswith("s"):
                interval_seconds = int(duration_str[:-1])
        
        await client.finish_background(
            name=name,
            cmd=cmd,
            args=cmd_list[1:],
            cwd=cwd,
            env=env,
            description=description,
            icon=icon_path,
            schedule=schedule_type,
            interval_seconds=interval_seconds,
        )
    
    print()
    print(f"Deployed: {name} ({app_type})")
    return 0


async def cmd_deploy(args, storage: StorageService) -> int:
    app_type = args.type
    app_dir = Path(args.path).resolve()
    
    if not app_dir.exists() or not app_dir.is_dir():
        print(f"Error: {app_dir} is not a valid directory")
        return 1
    
    print(f"Validating {app_type} app in {app_dir}...")
    valid, config, warnings = validate_app_dir(app_dir, app_type)
    if not valid:
        return 1
    
    for w in warnings:
        print(f"Warning: {w}")
    
    device = storage.state.last_used_device
    if not device:
        print("Error: No device connected. Run 'genesis connect <device>' first.")
        return 1
    
    token = storage.get_token(device)
    if not token:
        print(f"Error: No token for {device}. Run 'genesis connect {device}' first.")
        return 1
    
    print(f"Resolving {device}...")
    try:
        ip = await resolve_mdns(f"{device}.local")
    except RuntimeError as e:
        print(f"Error: {e}")
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
        deploy_task = asyncio.create_task(_do_deploy(client, config, app_dir, app_type, device))
        return await deploy_task
    except asyncio.CancelledError:
        print("Discarding build session...")
        if client.app_uuid:
            try:
                await client.discard()
                print("Session discarded.")
            except Exception:
                pass
        return 130
    except Exception as e:
        print(f"Error: {e}")
        if client.app_uuid:
            print("Discarding build session...")
            try:
                await client.discard()
            except Exception:
                pass
        return 1
    finally:
        loop.remove_signal_handler(signal.SIGINT)
        await client.close()


def cmd_list(args, storage: StorageService) -> int:
    what = args.what
    if what == "apps":
        print("list apps")
        print("(not implemented yet)")
    elif what == "devices":
        devices = storage.list_devices()
        if not devices:
            print("No connected devices")
        else:
            print("Connected devices:")
            for d in devices:
                marker = " (last used)" if d == storage.state.last_used_device else ""
                print(f"  {d}{marker}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="genesis",
        description="Genesis - TruffleOS SDK CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    p_connect = subparsers.add_parser("connect", help="Connect to a Truffle device")
    p_connect.add_argument("device", help="Device name (e.g. truffle-6272)")

    p_disconnect = subparsers.add_parser("disconnect", help="Disconnect from a device")
    p_disconnect.add_argument(
        "target", help="Device name or 'all' to clear all credentials"
    )

    p_deploy = subparsers.add_parser("deploy", help="Deploy an app to the device")
    p_deploy.add_argument(
        "type", choices=["ambient", "focus"], help="App type (ambient or focus)"
    )
    p_deploy.add_argument("path", help="Path to app directory")

    p_list = subparsers.add_parser("list", help="List apps or devices")
    p_list.add_argument(
        "what", choices=["apps", "devices"], help="What to list (apps or devices)"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    storage = StorageService()

    if args.command == "connect":
        return asyncio.run(cmd_connect(args, storage))
    elif args.command == "disconnect":
        return cmd_disconnect(args, storage)
    elif args.command == "deploy":
        return asyncio.run(cmd_deploy(args, storage))
    elif args.command == "list":
        return cmd_list(args, storage)

    return 0


if __name__ == "__main__":
    sys.exit(main())
