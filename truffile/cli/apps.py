import asyncio
import json
import sys

from truffile.storage import StorageService
from truffile.client import TruffleClient

from .connect import _resolve_connected_device
from .app_types import canonical_app_type
from .output import emit_error, emit_json, error_payload, ok_payload
from .ui import C, DOT, CROSS, CHECK, Spinner, error, warn, success


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
    kind = _app_kind(app)
    return {
        "name": app.metadata.name,
        "bundle_id": getattr(app.metadata, "bundle_id", ""),
        "uuid": app.uuid,
        "type": canonical_app_type(kind),
        "kind": kind,
    }


async def cmd_list_apps(args, storage: StorageService) -> int:
    json_out = bool(getattr(args, "json", False))
    device, ip = await _resolve_connected_device(storage, quiet=json_out)
    if not device or not ip:
        if json_out:
            return emit_error(
                "device_unreachable",
                "The connected Truffle device could not be resolved",
                retryable=True,
                next_action="Run truffile scan --json, then reconnect if needed",
            )
        return 1

    token = storage.get_token(device)
    if not token:
        if json_out:
            return emit_error(
                "missing_token",
                f"No saved session token for {device}",
                device=device,
                next_action=f"Run truffile connect {device} --user-id <user-id> --json",
            )
        error(f"No token for {device}")
        print(f"  {C.DIM}Run: truffile connect {device}{C.RESET}")
        return 1

    spinner = None
    if not json_out:
        spinner = Spinner(f"Connecting to {device}")
        spinner.start()

    address = f"{ip}:80"
    client = TruffleClient(address, token=token, app_id=storage.app_id_for_device(device))

    try:
        await client.connect()
        apps = await client.get_all_apps()
        if spinner:
            spinner.stop(success=True)

        if json_out:
            emit_json(ok_payload(device=device, apps=[_app_summary(app) for app in apps]))
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
            return emit_error("list_apps_failed", str(e), retryable=True, device=device)
        return 1
    finally:
        await client.close()

async def cmd_delete(args, storage: StorageService) -> int:
    json_out = bool(getattr(args, "json", False))
    dry_run = bool(getattr(args, "dry_run", False))
    confirmed = bool(getattr(args, "yes", False))
    non_interactive = bool(getattr(args, "non_interactive", False)) or json_out

    device, ip = await _resolve_connected_device(storage, quiet=json_out)
    if not device or not ip:
        if json_out:
            return emit_error(
                "device_unreachable",
                "The connected Truffle device could not be resolved",
                retryable=True,
                next_action="Run truffile scan --json, then reconnect if needed",
            )
        return 1

    token = storage.get_token(device)
    if not token:
        if json_out:
            return emit_error(
                "missing_token",
                f"No saved session token for {device}",
                device=device,
                next_action=f"Run truffile connect {device} --user-id <user-id> --json",
            )
        error(f"No token for {device}")
        print(f"  {C.DIM}Run: truffile connect {device}{C.RESET}")
        return 1

    spinner = None if json_out else Spinner(f"Connecting to {device}")
    if spinner:
        spinner.start()

    address = f"{ip}:80"
    client = TruffleClient(address, token=token, app_id=storage.app_id_for_device(device))

    try:
        await client.connect()
        apps = await client.get_all_apps()
        if spinner:
            spinner.stop(success=True)

        all_apps = []
        for app in apps:
            kind = _app_kind(app)
            desc = app.metadata.description.strip().split('\n')[0][:55] if app.metadata.description else ""
            all_apps.append((kind, app.uuid, app.metadata.name, desc))

        if not all_apps:
            if json_out:
                emit_json(ok_payload(device=device, dry_run=dry_run, apps=[], deleted=[]))
                return 0
            print(f"  {C.DIM}No apps installed{C.RESET}")
            return 0

        if not json_out:
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
        elif not sys.stdin.isatty() and not json_out:
            raw = sys.stdin.read().strip()
        elif non_interactive:
            raw = None
        else:
            raw = None

        if raw is not None:
            to_delete, selection_error = _resolve_delete_selection(raw, all_apps)
            if to_delete is None:
                # Invalid / out-of-range — fall back to interactive when possible.
                if sys.stdin.isatty() and not non_interactive:
                    if selection_error:
                        warn(selection_error)
                    warn("Invalid selection, switching to interactive prompt")
                    to_delete = _prompt_delete_interactive(len(all_apps))
                else:
                    if json_out:
                        return emit_error(
                            "invalid_selection",
                            selection_error or "Invalid app selection",
                            device=device,
                        )
                    error(selection_error or "Invalid selection")
                    return 1
        elif non_interactive:
            apps_payload = [
                {"name": name, "uuid": uuid, "type": canonical_app_type(kind), "kind": kind}
                for kind, uuid, name, _desc in all_apps
            ]
            if json_out:
                return emit_error(
                    "selection_required",
                    "Choose one or more installed apps to delete",
                    device=device,
                    apps=apps_payload,
                    next_action="Run truffile delete <name-or-uuid> --dry-run --json",
                )
            error("An app selection is required in non-interactive mode")
            return 1
        else:
            to_delete = _prompt_delete_interactive(len(all_apps))

        if not to_delete:
            if json_out:
                emit_json(ok_payload(device=device, dry_run=dry_run, apps=[], deleted=[]))
            return 0

        targets = [
            {
                "name": all_apps[idx][2],
                "uuid": all_apps[idx][1],
                "type": canonical_app_type(all_apps[idx][0]),
                "kind": all_apps[idx][0],
            }
            for idx in to_delete
        ]

        if dry_run:
            if json_out:
                emit_json(ok_payload(device=device, dry_run=True, apps=targets))
            else:
                print(f"{C.BOLD}Dry Run: Apps To Delete{C.RESET}")
                for target in targets:
                    print(f"  {C.CYAN}{DOT}{C.RESET} {target['name']} {C.DIM}({target['kind']}){C.RESET}")
                print()
                success("Dry run complete (no device changes made)")
            return 0

        if not confirmed:
            if non_interactive or not sys.stdin.isatty():
                if json_out:
                    return emit_error(
                        "confirmation_required",
                        "Deletion requires explicit confirmation",
                        device=device,
                        apps=targets,
                        next_action="Review the plan, then rerun the command with --yes --json",
                    )
                error("Deletion requires --yes in non-interactive mode")
                return 1
            names = ", ".join(target["name"] for target in targets)
            try:
                answer = input(f"Delete {names}? [y/N]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print()
                return 130
            if answer not in {"y", "yes"}:
                info = "Deletion cancelled"
                print(f"  {C.DIM}{info}{C.RESET}")
                return 0

        if not json_out:
            print()
        deleted = 0
        deleted_apps: list[dict[str, str]] = []
        failures: list[dict[str, str]] = []
        for idx in to_delete:
            kind, uuid, name, _ = all_apps[idx]
            spinner = None if json_out else Spinner(f"Deleting {name}")
            if spinner:
                spinner.start()
            try:
                await client.delete_app(uuid)
                if spinner:
                    spinner.stop(success=True)
                deleted += 1
                deleted_apps.append({
                    "name": name,
                    "uuid": uuid,
                    "type": canonical_app_type(kind),
                    "kind": kind,
                })
            except Exception as e:
                if spinner:
                    spinner.fail(f"Failed to delete {name}: {e}")
                failures.append({"name": name, "uuid": uuid, "message": str(e)})

        if json_out:
            if failures:
                emit_json(error_payload(
                    "delete_failed",
                    "One or more apps could not be deleted",
                    device=device,
                    deleted=deleted_apps,
                    failures=failures,
                ))
                return 1
            emit_json(ok_payload(device=device, deleted=deleted_apps))
            return 0

        print()
        success(f"Deleted {deleted} app(s)")
        return 1 if failures else 0

    except Exception as e:
        if spinner:
            spinner.fail(str(e))
        if json_out:
            return emit_error("delete_failed", str(e), retryable=True, device=device)
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
            emit_json(ok_payload(
                devices=[
                    {"name": device, "active": device == storage.state.last_used_device}
                    for device in devices
                ],
            ))
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
