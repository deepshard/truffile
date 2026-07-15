import asyncio
import json
import sys

from truffile.storage import StorageService
from truffile.client import TruffleClient

from .connect import _grpc_address, _resolve_connected_device
from .ui import C, DOT, Spinner, error, warn, success


def _app_kind(app) -> str:
    if app.HasField("foreground") and app.HasField("background"):
        return "both"
    if app.HasField("foreground"):
        return "focus"
    if app.HasField("background"):
        return "ambient"
    return "unknown"


def _app_slug(name: str) -> str:
    return name.strip().lower().replace(" ", "-")


def _app_summary(app) -> dict[str, str]:
    return {
        "name": app.metadata.name,
        "uuid": app.uuid,
    }


async def cmd_list_apps(args, storage: StorageService) -> int:
    json_out = bool(getattr(args, "json", False))
    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return 1

    token = storage.get_token(device)
    if not token:
        error(f"No token for {device}")
        print(f"  {C.DIM}Run: truffile connect {device}{C.RESET}")
        return 1

    spinner = None
    if not json_out:
        spinner = Spinner(f"Connecting to {device}")
        spinner.start()

    address = _grpc_address(ip)
    client = TruffleClient(address, token=token, app_id=storage.app_id_for_device(device))

    try:
        await client.connect()
        apps = await client.get_all_apps()
        if spinner:
            spinner.stop(success=True)

        if json_out:
            print(json.dumps({"apps": [_app_summary(app) for app in apps]}, indent=2))
            return 0

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
        if spinner:
            spinner.fail(str(e))
        else:
            error(str(e))
        return 1
    finally:
        await client.close()

async def cmd_delete(args, storage: StorageService) -> int:
    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return 1

    token = storage.get_token(device)
    if not token:
        error(f"No token for {device}")
        print(f"  {C.DIM}Run: truffile connect {device}{C.RESET}")
        return 1

    spinner = Spinner(f"Connecting to {device}")
    spinner.start()

    address = _grpc_address(ip)
    client = TruffleClient(address, token=token, app_id=storage.app_id_for_device(device))

    try:
        await client.connect()
        apps = await client.get_all_apps()
        spinner.stop(success=True)

        all_apps = []
        for app in apps:
            kind = _app_kind(app)
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

        # Resolve selection from CLI args, piped stdin, or interactive prompt.
        selection_args = getattr(args, "selection", []) or []

        if selection_args:
            raw = " ".join(selection_args)
        elif not sys.stdin.isatty():
            raw = sys.stdin.read().strip()
        else:
            raw = None

        if raw is not None:
            to_delete, selection_error = _resolve_delete_selection(raw, all_apps)
            if to_delete is None:
                # Invalid / out-of-range — fall back to interactive when possible.
                if sys.stdin.isatty():
                    if selection_error:
                        warn(selection_error)
                    warn("Invalid selection, switching to interactive prompt")
                    to_delete = _prompt_delete_interactive(len(all_apps))
                else:
                    error(selection_error or "Invalid selection")
                    return 1
        else:
            to_delete = _prompt_delete_interactive(len(all_apps))

        if not to_delete:
            return 0

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


def _parse_delete_selection(raw: str, count: int) -> list[int] | None:
    """Parse a selection string into 0-based indices.

    Accepts 'all', or 1-based numbers separated by spaces and/or commas
    (e.g. '1,3,5', '1 2', '1, 2, 3').  Returns ``None`` when input is
    unparseable or any index is out of range.
    """
    raw = raw.strip()
    if not raw:
        return []
    if raw.lower() == "all":
        return list(range(count))

    parts = raw.replace(",", " ").split()
    indices: list[int] = []
    for p in parts:
        try:
            idx = int(p) - 1
        except ValueError:
            return None
        if idx < 0 or idx >= count:
            return None
        indices.append(idx)
    return indices or None


def _resolve_app_ref(ref: str, all_apps: list[tuple[str, str, str, str]]) -> tuple[int | None, str | None]:
    ref_s = ref.strip()
    if not ref_s:
        return None, None
    ref_l = ref_s.lower()

    for i, (_kind, uuid, _name, _desc) in enumerate(all_apps):
        if uuid == ref_s:
            return i, None

    exact_matches = [
        i for i, (_kind, _uuid, name, _desc) in enumerate(all_apps)
        if name.lower() == ref_l or _app_slug(name) == ref_l
    ]
    if len(exact_matches) == 1:
        return exact_matches[0], None
    if len(exact_matches) > 1:
        return None, f"Ambiguous app name: {ref_s}"

    substring_matches = [
        i for i, (_kind, _uuid, name, _desc) in enumerate(all_apps)
        if ref_l in name.lower()
    ]
    if len(substring_matches) == 1:
        return substring_matches[0], None
    if len(substring_matches) > 1:
        names = ", ".join(all_apps[i][2] for i in substring_matches)
        return None, f"Ambiguous app name '{ref_s}' matched: {names}"

    return None, f"No installed app matched: {ref_s}"


def _resolve_delete_selection(
    raw: str,
    all_apps: list[tuple[str, str, str, str]],
) -> tuple[list[int] | None, str | None]:
    raw = raw.strip()
    if not raw:
        return [], None

    numeric = _parse_delete_selection(raw, len(all_apps))
    if numeric is not None:
        return numeric, None

    refs = [part.strip() for part in raw.split(",") if part.strip()]
    if not refs:
        return [], None

    if len(refs) == 1:
        idx, err = _resolve_app_ref(refs[0], all_apps)
        if idx is not None:
            return [idx], None
        return None, err

    indices: list[int] = []
    for ref in refs:
        idx, err = _resolve_app_ref(ref, all_apps)
        if idx is None:
            return None, err
        indices.append(idx)
    return list(dict.fromkeys(indices)), None


def _prompt_delete_interactive(count: int) -> list[int] | None:
    """Show an interactive prompt and return parsed indices."""
    try:
        choice = input("Select apps to delete (e.g. 1,3,5 or 'all'): ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return None
    return _parse_delete_selection(choice, count)


def cmd_list(args, storage: StorageService) -> int:
    what = args.what
    if what == "apps":
        return _run_async(cmd_list_apps(args, storage))
    elif what == "devices":
        devices = storage.list_devices()
        if bool(getattr(args, "json", False)):
            print(
                json.dumps(
                    {
                        "devices": [
                            {
                                "name": device,
                                "active": device == storage.state.last_used_device,
                            }
                            for device in devices
                        ]
                    },
                    indent=2,
                )
            )
            return 0
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


def _run_async(coro):
    return asyncio.run(coro)
