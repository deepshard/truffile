import json

from truffile.client import TruffleClient
from truffile.storage import StorageService

from .connect import _resolve_connected_device
from .ui import C, DOT, Spinner, error, success, warn


def _reset_mode(args) -> str:
    return "hard" if bool(getattr(args, "hard", False)) else "soft"


def _confirm_hard_reset() -> bool:
    print()
    warn("Hard reset clears persisted Convo state for the current user.")
    print(f"  {C.DIM}{DOT} Soft reset restarts the agent/runtime path and keeps Convo history.{C.RESET}")
    print(f"  {C.DIM}{DOT} Hard reset clears Convo nodes, threads, and runtime state, then recreates core threads.{C.RESET}")
    print()
    try:
        answer = input(f"{C.CYAN}?{C.RESET} Continue with hard reset? Type 'yes': ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    return answer == "yes"


async def cmd_convo_reset(args, storage: StorageService) -> int:
    json_out = bool(getattr(args, "json", False))
    hard = bool(getattr(args, "hard", False))
    force = bool(getattr(args, "force", False))

    if hard and not force and json_out:
        print(json.dumps({"error": "hard reset requires --force when --json is used"}))
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

    if hard and not force:
        if not _confirm_hard_reset():
            warn("Convo reset canceled")
            return 1

    spinner = None
    if not json_out:
        spinner = Spinner(f"Resetting Convo ({_reset_mode(args)})")
        spinner.start()

    client = TruffleClient(f"{ip}:80", token=token, app_id=storage.app_id_for_device(device))
    try:
        await client.connect()
        await client.reset_convo(hard=hard)
        if spinner:
            spinner.stop(success=True)
        if json_out:
            print(json.dumps({"mode": _reset_mode(args)}))
        else:
            success(f"Convo {_reset_mode(args)} reset complete")
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
