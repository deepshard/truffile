import argparse
import asyncio
import sys
from pathlib import Path

from .ui import C, MUSHROOM, print_help


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def main() -> int:
    parser = argparse.ArgumentParser(prog="truffile", add_help=False)
    sub = parser.add_subparsers(dest="command")

    # scan
    scan_p = sub.add_parser("scan", help="scan for truffle devices")
    scan_p.add_argument("--timeout", type=int, default=5)

    # connect
    conn_p = sub.add_parser("connect", help="connect to a truffle")
    conn_p.add_argument("device", help="device name (e.g. truffle-1234)")

    # disconnect
    disc_p = sub.add_parser("disconnect", help="disconnect from device(s)")
    disc_p.add_argument("device", nargs="?", default="all")

    # create
    create_p = sub.add_parser("create", help="scaffold a new app")
    create_p.add_argument("name", nargs="?")

    # validate
    val_p = sub.add_parser("validate", help="validate app directory")
    val_p.add_argument("path", nargs="?", default=".")

    # deploy
    dep_p = sub.add_parser("deploy", help="deploy app to device")
    dep_p.add_argument("path", nargs="?", default=".")
    dep_p.add_argument("--shell", action="store_true")
    dep_p.add_argument("--no-finalize", action="store_true")

    # list
    list_p = sub.add_parser("list", help="list apps or devices")
    list_p.add_argument("what", choices=["apps", "devices"])

    # delete
    del_p = sub.add_parser("delete", help="delete app from device")
    del_p.add_argument("app", nargs="?")

    # models
    sub.add_parser("models", help="list inference models")

    # chat
    chat_p = sub.add_parser("chat", help="interactive chat")
    chat_p.add_argument("--model", type=str, default=None)
    chat_p.add_argument("--system", type=str, default=None)
    chat_p.add_argument("--no-stream", action="store_true")
    chat_p.add_argument("--no-tools", action="store_true")
    chat_p.add_argument("--mcp", type=str, action="append", default=None)

    # help
    sub.add_parser("help", help="show help")

    args = parser.parse_args()

    if args.command is None or args.command == "help":
        print_help()
        return 0

    from truffile.storage import StorageService
    storage = StorageService()

    if args.command == "scan":
        from .connect import cmd_scan
        return run_async(cmd_scan(args, storage))
    elif args.command == "connect":
        from .connect import cmd_connect
        return run_async(cmd_connect(args, storage))
    elif args.command == "disconnect":
        from .connect import cmd_disconnect
        return cmd_disconnect(args, storage)
    elif args.command == "create":
        from .create import cmd_create
        return cmd_create(args)
    elif args.command == "validate":
        from .validate import cmd_validate
        return cmd_validate(args)
    elif args.command == "deploy":
        from .deploy import cmd_deploy
        return run_async(cmd_deploy(args, storage))
    elif args.command == "list":
        from .apps import cmd_list
        return cmd_list(args, storage)
    elif args.command == "delete":
        from .apps import cmd_delete
        return run_async(cmd_delete(args, storage))
    elif args.command == "models":
        from .models import cmd_models
        return run_async(cmd_models(storage))
    elif args.command == "chat":
        from .chat import cmd_chat
        return run_async(cmd_chat(args, storage))

    print_help()
    return 1
