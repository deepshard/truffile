import json

from truffile.client import TruffleClient
from truffile.storage import StorageService

from .connect import _resolve_connected_device
from .ui import C, DOT, Spinner, error, success, warn


def _identity_dict(identity) -> dict[str, str]:
    return {
        "user_id": str(getattr(identity, "user_id", "") or ""),
        "username": str(getattr(identity, "username", "") or ""),
    }


def _print_identity(identity: dict[str, str]) -> None:
    user_id = identity.get("user_id") or "(unknown)"
    username = identity.get("username") or "(not set)"
    print(f"  {C.DIM}{DOT} User ID: {user_id}{C.RESET}")
    print(f"  {C.DIM}{DOT} Username: {username}{C.RESET}")


def _confirm_clear_other_users(identity: dict[str, str]) -> bool:
    print()
    warn("This action will delete old users that are not associated with your current account:")
    _print_identity(identity)
    print()
    try:
        answer = input(f"{C.CYAN}?{C.RESET} Clear other users? Type 'yes': ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    return answer == "yes"


async def cmd_users_clear_other(args, storage: StorageService) -> int:
    json_out = bool(getattr(args, "json", False))
    force = bool(getattr(args, "force", False))

    if json_out and not force:
        print(json.dumps({"error": "clear-other requires --force when --json is used"}))
        return 1

    device, ip = await _resolve_connected_device(storage)
    if not device or not ip:
        return 1

    token = storage.get_token(device)
    if not token:
        if json_out:
            print(json.dumps({"error": f"no token for {device}"}))
        else:
            error(f"No token for {device}")
            print(f"  {C.DIM}Run: truffile connect {device}{C.RESET}")
        return 1

    spinner = None
    if not json_out:
        spinner = Spinner(f"Connecting to {device}")
        spinner.start()

    client = TruffleClient(f"{ip}:80", token=token, app_id=storage.app_id_for_device(device))
    try:
        await client.connect()
        identity = _identity_dict(await client.get_current_user_identity())
        if spinner:
            spinner.stop(success=True)
            spinner = None

        if not force and not json_out:
            if not _confirm_clear_other_users(identity):
                warn("Clear other users canceled")
                return 1
        if not json_out:
            spinner = Spinner("Clearing other users")
            spinner.start()
        response = await client.clear_other_users_data()
        count = int(getattr(response, "num_users_cleared", 0) or 0)
        if spinner:
            spinner.stop(success=True)
        if json_out:
            print(json.dumps({"cleared": count, **identity}))
        else:
            noun = "user" if count == 1 else "users"
            success(f"Cleared {count} other {noun}")
        return 0
    except Exception as exc:
        if spinner:
            spinner.fail(str(exc))
        elif json_out:
            print(json.dumps({"error": str(exc)}))
        else:
            error(str(exc))
        return 1
    finally:
        await client.close()
