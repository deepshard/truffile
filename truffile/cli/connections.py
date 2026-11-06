"""Manage an explicitly selected installed account through the public RPCs."""

import contextlib
import json
import sys

import grpc

from truffile.client import TruffleClient
from .apps import _app_slug, _app_summary
from .connect import _resolve_connected_device
from .prompts import choose, confirm

PERMISSIONS = {"default": 0, "read-only": 1, "read-write": 3, "auto-review": 11}


def select_app(apps, ref):
    exact = [app for app in apps if app.uuid == ref or app.metadata.bundle_id == ref]
    matches = exact or [
        app for app in apps
        if ref.casefold() in (app.metadata.name.casefold(), _app_slug(app.metadata.name))
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one app matching {ref!r}; found {len(matches)}. Use its UUID.")
    return matches[0]


def select_connection(app, ref):
    matches = [c for c in app.connections if c.connection_id == ref]
    if not matches:
        matches = [
            c for c in app.connections
            if (c.is_default if ref == "default" else c.alias.casefold() == ref.casefold())
        ]
    if len(matches) != 1:
        raise ValueError(f"Expected one connection matching {ref!r}; found {len(matches)}. Use its connection ID.")
    return matches[0]


async def choose_app(apps, ref, args):
    if ref:
        try:
            return select_app(apps, ref)
        except ValueError:
            apps = [app for app in apps if ref == app.uuid or ref == app.metadata.bundle_id
                    or ref.casefold() in (app.metadata.name.casefold(), _app_slug(app.metadata.name))]
    return await choose(apps, question="Which app?", label=lambda app: f"{app.metadata.name} ({app.uuid})", args=args)


async def choose_connection(app, ref, args):
    if ref:
        try:
            return select_connection(app, ref)
        except ValueError:
            accounts = [c for c in app.connections if c.alias.casefold() == ref.casefold()]
    else:
        accounts = list(app.connections)
    return await choose(accounts, question=f"Which account for {app.metadata.name}?",
                        label=lambda c: f"{c.alias or 'Unnamed account'} ({c.connection_id})", args=args)


async def cmd_connections(args, storage):
    client = None
    try:
        with contextlib.redirect_stdout(sys.stderr):
            device, ip = await _resolve_connected_device(storage)
        if not device or not ip:
            raise ValueError("No reachable device; run truffile connect <device>")
        token = storage.get_token(device)
        if not token:
            raise ValueError("No saved session for the selected device")
        client = TruffleClient(f"{ip}:80", token, app_id=storage.app_id_for_device(device))
        await client.connect()
        app = await choose_app(await client.get_all_apps(), args.app, args)
        action = args.connections_command
        if action in {"add", "reconnect"}:
            from truffile.deploy.native import install_native
            from .native import InstallPrompts
            connection = await choose_connection(app, args.connection, args) if action == "reconnect" else None
            await install_native(client, mode=action, app_uuid=app.uuid,
                connection_id=connection.connection_id if connection else None,
                handle_modal=InstallPrompts(args, client.address),
                progress=lambda text: print(text, file=sys.stderr), timeout=getattr(args, "timeout", 900))
            app = select_app(await client.get_all_apps(), app.uuid)
        elif action != "list":
            connection = await choose_connection(app, args.connection, args)
            if action == "rename":
                app = await client.update_connection(app.uuid, connection.connection_id, alias=args.alias)
            elif action == "permissions":
                notes = args.notes if args.notes is not None else connection.permission.auto_review_notes
                app = await client.update_connection(
                    app.uuid, connection.connection_id,
                    permission_flags=PERMISSIONS[args.mode], auto_review_notes=notes,
                )
            elif action == "delete":
                await confirm(f"Delete {connection.alias or connection.connection_id} from {app.metadata.name}?", args)
                app = await client.delete_connection(app.uuid, connection.connection_id)
        result = {"status": "ok", "app": _app_summary(app)}
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"{app.metadata.name} ({app.uuid})")
            for c in result["app"]["connections"]:
                permission = c.get("permission", {})
                flags = permission.get("flags", 0)
                mode = next((label for label, value in PERMISSIONS.items() if value == flags), f"flags={flags}")
                print(f"  {c['connection_id']}  {c['alias']}  {c['status']}  {mode}")
        return 0
    except Exception as exc:
        message = exc.details() if isinstance(exc, grpc.aio.AioRpcError) else str(exc)
        result = {"status": "error", "error": message}
        if isinstance(exc, grpc.aio.AioRpcError):
            result["rpc_code"] = exc.code().name
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            await client.close()
