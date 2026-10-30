"""User-facing native install prompts and local bundle deployment."""

import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import grpc
from aiohttp import web
from truffle.os.installer_pb2 import AppInstallUserAction

from truffile.client import TruffleClient
from truffile.deploy.native import install_native, prepare_bundle
from truffile.deploy.steps.oauth import _parse_callback
from .connect import _resolve_connected_device
from .prompts import confirm, interactive, prompt


class InteractionRequired(ValueError):
    pass


class InstallPrompts:
    def __init__(self, args, address):
        self.args = args
        self.address = address
        self.answers = {}
        if getattr(args, "answers_file", None):
            self.answers = json.loads(Path(args.answers_file).read_text())
            if not isinstance(self.answers, dict) or not all(isinstance(v, str) for v in self.answers.values()):
                raise ValueError("--answers-file must contain a JSON object of field names to string values")

    async def oauth(self, modal):
        value = modal.oauth_modal
        if not interactive(self.args):
            raise InteractionRequired("OAuth needs browser sign-in; rerun interactively to complete authorization")
        if urlparse(value.auth_url).scheme not in {"http", "https"}:
            raise ValueError("Installer returned an invalid authorization URL")
        # A local callback is optional: a user signing in on another computer
        # can still paste the callback URL or the provider's approval code.
        callback = asyncio.get_running_loop().create_future()
        runner = None
        if os.name == "posix" and value.HasField("loopback_callback"):
            redirect = urlparse(value.loopback_callback.redirect_uri)
            if redirect.scheme == "http" and redirect.hostname in {"localhost", "127.0.0.1", "::1"} and redirect.port:
                async def receive(request):
                    try:
                        code = _parse_callback(str(request.rel_url), expected_state=value.state)
                    except RuntimeError:
                        return web.Response(status=400, text="Invalid authorization callback. Return to the terminal.")
                    if not callback.done():
                        callback.set_result(code)
                    return web.Response(text="Authorization received. You can return to the terminal.")
                app = web.Application()
                app.router.add_get(redirect.path or "/", receive)
                runner = web.AppRunner(app, access_log=None)
                await runner.setup()
                try:
                    await web.TCPSite(runner, redirect.hostname, redirect.port).start()
                except OSError:
                    await runner.cleanup()
                    runner = None
                    print("Local callback port unavailable; paste the callback URL instead.", file=sys.stderr)
        print(value.instructions or f"Sign in to {value.provider}", file=sys.stderr)
        print(value.auth_url, file=sys.stderr)
        pasted = asyncio.create_task(prompt("Paste the callback URL or approval code (or finish the local browser callback): ", secret=True))
        try:
            done, _ = await asyncio.wait({callback, pasted}, return_when=asyncio.FIRST_COMPLETED)
            code = callback.result() if callback in done else _parse_callback(pasted.result(), expected_state=value.state)
            action = AppInstallUserAction()
            action.oauth.code, action.oauth.state = code, value.state
            return action
        finally:
            pasted.cancel()
            await asyncio.gather(pasted, return_exceptions=True)
            callback.cancel()
            if runner:
                await runner.cleanup()

    async def __call__(self, modal):
        action = AppInstallUserAction()
        if modal.HasField("welcome_modal"):
            print(modal.welcome_modal.welcome_message, file=sys.stderr)
            action.next.SetInParent()
        elif modal.HasField("text_fields_modal"):
            print(modal.text_fields_modal.instructions, file=sys.stderr)
            for name, field in modal.text_fields_modal.fields.items():
                key = f"{modal.step_index}.{name}"
                if key in self.answers or name in self.answers:
                    answer = self.answers.get(key, self.answers.get(name))
                elif interactive(self.args):
                    label = field.label or name
                    hint = " [default available]" if field.default_value else ""
                    answer = await prompt(f"{label}{hint}: ", secret=field.is_password)
                    answer = answer or field.default_value
                else:
                    raise InteractionRequired(f"Input required for {name!r}; use interactive mode or --answers-file")
                action.text_fields.field_responses[name] = answer
        elif modal.HasField("oauth_modal"):
            return await self.oauth(modal)
        elif modal.HasField("vnc_modal"):
            if not interactive(self.args):
                raise InteractionRequired("Browser setup is required; rerun interactively")
            value = modal.vnc_modal
            route = value.vnc_uri_path
            if not route.startswith("/") or route.startswith("//") or "\\" in route:
                raise ValueError("Installer returned an invalid browser setup path")
            print(value.instructions, file=sys.stderr)
            print(f"http://{self.address}{route}", file=sys.stderr)
            if value.closes_on_complete:
                return None
            await prompt("Complete browser setup, then press Enter: ")
            action.next.SetInParent()
        else:
            raise InteractionRequired("This installer interaction is not supported by this CLI")
        return action


def print_error(args, exc):
    message = exc.details() if isinstance(exc, grpc.aio.AioRpcError) else str(exc)
    if getattr(args, "json", False):
        print(json.dumps({"status": "error", "error": "interaction_required" if isinstance(exc, InteractionRequired) else "install_failed", "message": message}))
    else:
        print(f"Error: {message}", file=sys.stderr)
    return 1


async def cmd_native_deploy(args, storage):
    from .connections import choose_app
    client = None
    try:
        mode = "update" if getattr(args, "update", False) else "replace" if getattr(args, "replace", False) else "install"
        with prepare_bundle(Path(args.path or "."), exclude_paths=[getattr(args, "answers_file", None)]) as bundle:
            meta = bundle.config["metadata"]
            if getattr(args, "dry_run", False):
                result = {"status": "ok", "dry_run": True, "mode": mode, "app": {"name": meta["name"], "bundle_id": meta["bundle_id"]},
                          "bundle_sha256": bundle.sha256, "validation": "local bundle preflight; full manifest validation runs on firmware"}
                print(json.dumps(result, indent=2) if getattr(args, "json", False) else f"Bundle ready: {meta['name']} ({mode}). Firmware will validate the full install plan.")
                return 0
            with contextlib.redirect_stdout(sys.stderr):
                device, ip = await _resolve_connected_device(storage)
            if not device or not ip or not storage.get_token(device):
                raise ValueError("No connected device; run truffile connect <device>")
            client = TruffleClient(f"{ip}:80", storage.get_token(device), app_id=storage.app_id_for_device(device))
            await client.connect()
            apps = await client.get_all_apps()
            matches = [app for app in apps if app.metadata.bundle_id == meta["bundle_id"]]
            target = None
            if matches and mode == "install":
                raise ValueError(f"{meta['name']} is installed. Use --update to preserve accounts or --replace for fresh setup.")
            if mode in {"update", "replace"}:
                target = await choose_app(matches, meta["bundle_id"], args)
            if mode == "replace":
                await confirm(f"Replacing {target.metadata.name} resets its accounts and saved setup.", args)
            prompts = InstallPrompts(args, client.address)
            result = await install_native(client, mode=mode, bundle=bundle,
                app_uuid=target.uuid if target else None, handle_modal=prompts,
                progress=lambda text: print(text, file=sys.stderr), timeout=getattr(args, "timeout", 900))
            # Verify the committed bundle, not merely a refresh acknowledgement.
            installed = next((app for app in await client.get_all_apps() if app.uuid == result["app_uuid"]), None)
            if installed is None or installed.installed_bundle.release.bundle_sha256 != bundle.sha256:
                raise RuntimeError("Installer finished but the requested bundle is not visible. Inspect the app before retrying.")
            print(json.dumps({"status": "ok", **result}, indent=2) if getattr(args, "json", False) else f"Ready: {installed.metadata.name} ({mode})")
            return 0
    except Exception as exc:
        return print_error(args, exc)
    finally:
        if client:
            await client.close()
