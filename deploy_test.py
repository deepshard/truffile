#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path
import yaml
from truffile import TruffleClient

# add your truffle ip (get it with ping truffle-xxxx.local)
DEVICE_ADDRESS = "192.168.1.32:80"
TOKEN = "go get your token"


def parse_truffile(app_dir: Path) -> dict:
    truffile = app_dir / "truffile.yaml"
    if not truffile.exists():
        raise FileNotFoundError(f"No truffile.yaml in {app_dir}")
    with open(truffile) as f:
        return yaml.safe_load(f)


async def deploy_focus_app(app_dir: Path):
    app_dir = Path(app_dir).resolve()
    config = parse_truffile(app_dir)
    meta = config["metadata"]
    
    name = meta["name"]
    description = meta.get("description", "")
    process = meta.get("process", {})
    cmd_list = process.get("cmd", ["python", "app.py"])
    cwd = process.get("working_directory", "/")
    env_dict = process.get("environment", {})
    env = [f"{k}={v}" for k, v in env_dict.items()]
    icon_file = meta.get("icon_file")
    icon_path = (app_dir / icon_file) if icon_file else None
    
    print(f"Deploying FOCUS app: {name}")
    print(f"  Directory: {app_dir}")
    
    client = TruffleClient(DEVICE_ADDRESS, token=TOKEN)
    await client.connect()
    print(f"  Connected to {DEVICE_ADDRESS}")
    
    await client.start_build()
    print(f"  Build session: {client.app_uuid}")
    
    try:
        for step in config.get("steps", []):
            if step["type"] == "files":
                for f in step.get("files", []):
                    src = app_dir / f["source"]
                    dest = f["destination"]
                    print(f"  Uploading {src.name} -> {dest}")
                    result = await client.upload(src, dest)
                    print(f"    {result.bytes} bytes")
            elif step["type"] == "bash":
                print(f"  Running: {step['name']}")
                r = await client.exec(step["run"])
                print(f"    Exit code: {r.exit_code}")
                if r.exit_code != 0:
                    for line in r.output[-10:]:
                        print(f"    {line}")
        
        print(f"  Finishing as foreground app...")
        await client.finish_foreground(
            name=name,
            cmd=cmd_list[0] if cmd_list[0].startswith("/") else f"/usr/bin/{cmd_list[0]}",
            args=cmd_list[1:],
            cwd=cwd,
            env=env,
            description=description,
            icon=icon_path,
        )
        print(f"Done! {name} deployed as focus app.")
        
    except Exception as e:
        print(f"Error: {e}")
        await client.discard()
        raise
    finally:
        await client.close()


async def deploy_ambient_app(app_dir: Path):
    app_dir = Path(app_dir).resolve()
    config = parse_truffile(app_dir)
    meta = config["metadata"]
    
    name = meta["name"]
    description = meta.get("description", "")
    process = meta.get("process", {})
    cmd_list = process.get("cmd", ["python", "app.py"])
    cwd = process.get("working_directory", "/")
    env_dict = process.get("environment", {})
    env = [f"{k}={v}" for k, v in env_dict.items()]
    icon_file = meta.get("icon_file")
    icon_path = (app_dir / icon_file) if icon_file else None
    
    schedule_cfg = meta.get("default_schedule", {})
    schedule_type = schedule_cfg.get("type", "interval")
    interval_seconds = 60
    daily_start_hour = None
    daily_end_hour = None
    
    if schedule_type == "interval":
        interval_cfg = schedule_cfg.get("interval", {})
        duration_str = interval_cfg.get("duration", "1m")
        if duration_str.endswith("m"):
            interval_seconds = int(duration_str[:-1]) * 60
        elif duration_str.endswith("h"):
            interval_seconds = int(duration_str[:-1]) * 3600
        elif duration_str.endswith("s"):
            interval_seconds = int(duration_str[:-1])
        
        sched = interval_cfg.get("schedule", {})
        # Skip daily window for now - let it run anytime
        # daily_window = sched.get("daily_window")
        # if daily_window and "-" in daily_window:
        #     start, end = daily_window.split("-")
        #     daily_start_hour = int(start.split(":")[0])
        #     daily_end_hour = int(end.split(":")[0])
    
    print(f"Deploying AMBIENT app: {name}")
    print(f"  Directory: {app_dir}")
    print(f"  Schedule: {schedule_type}, interval={interval_seconds}s")
    
    client = TruffleClient(DEVICE_ADDRESS, token=TOKEN)
    await client.connect()
    print(f"  Connected to {DEVICE_ADDRESS}")
    
    await client.start_build()
    print(f"  Build session: {client.app_uuid}")
    
    try:
        for step in config.get("steps", []):
            if step["type"] == "files":
                for f in step.get("files", []):
                    src = app_dir / f["source"]
                    dest = f["destination"]
                    print(f"  Uploading {src.name} -> {dest}")
                    result = await client.upload(src, dest)
                    print(f"    {result.bytes} bytes")
            elif step["type"] == "bash":
                print(f"  Running: {step['name']}")
                r = await client.exec(step["run"])
                print(f"    Exit code: {r.exit_code}")
                if r.exit_code != 0:
                    for line in r.output[-10:]:
                        print(f"    {line}")
        
        print(f"  Finishing as background app...")
        await client.finish_background(
            name=name,
            cmd=cmd_list[0] if cmd_list[0].startswith("/") else f"/usr/bin/{cmd_list[0]}",
            args=cmd_list[1:],
            cwd=cwd,
            env=env,
            description=description,
            icon=icon_path,
            schedule=schedule_type,
            interval_seconds=interval_seconds,
            daily_start_hour=daily_start_hour,
            daily_end_hour=daily_end_hour,
        )
        print(f"Done! {name} deployed as ambient app.")
        
    except Exception as e:
        print(f"Error: {e}")
        await client.discard()
        raise
    finally:
        await client.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python deploy_test.py <focus|ambient> <path-to-app-dir>")
        print()
        print("Examples:")
        print("  python deploy_test.py focus ./example-apps/focus/finance")
        print("  python deploy_test.py ambient ./example-apps/ambient/hedge")
        sys.exit(1)
    
    app_type = sys.argv[1].lower()
    app_path = Path(sys.argv[2])
    
    if app_type == "focus":
        asyncio.run(deploy_focus_app(app_path))
    elif app_type == "ambient":
        asyncio.run(deploy_ambient_app(app_path))
    else:
        print(f"Unknown type: {app_type}")
        print("Use 'focus' for foreground apps or 'ambient' for background apps")
        sys.exit(1)
