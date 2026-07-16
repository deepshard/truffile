import asyncio

from truffile.storage import StorageService
from truffile.client import TruffleClient, resolve_mdns, NewSessionStatus

from .in_container import probe_in_container_device
from .output import emit_error, emit_json, ok_payload
from .ui import C, DOT, Spinner, error, success, info


async def cmd_connect(args, storage: StorageService) -> int:
    json_out = bool(getattr(args, "json", False))
    non_interactive = bool(getattr(args, "non_interactive", False)) or json_out

    def fail(
        code: str,
        message: str,
        *,
        retryable: bool = False,
        next_action: str | None = None,
    ) -> int:
        if json_out:
            return emit_error(
                code,
                message,
                retryable=retryable,
                next_action=next_action,
                device=getattr(args, "device", None),
            )
        error(message)
        return 1

    approval_timeout = getattr(args, "approval_timeout", None)
    if approval_timeout is not None and float(approval_timeout) <= 0:
        return fail("invalid_args", "--approval-timeout must be greater than zero")

    # In-container short-circuit: the runtime already gave us a session
    # token + gRPC address, so there is nothing to pair.
    ic_info = probe_in_container_device()
    if ic_info is not None:
        if json_out:
            emit_json(ok_payload(
                state="paired",
                device=ic_info.device_name,
                address=ic_info.grpc_address,
                execution_context="truffle_container",
                firmware_version=ic_info.firmware_version or None,
                probe_incomplete=bool(ic_info.probe_failed),
            ))
            return 0
        success(f"Already connected to {C.BOLD}{ic_info.device_name}{C.RESET} via in-container session")
        print(f"  {C.DIM}address:  {ic_info.grpc_address}{C.RESET}")
        if ic_info.firmware_version:
            print(f"  {C.DIM}firmware: {ic_info.firmware_version}{C.RESET}")
        if ic_info.probe_failed:
            print(f"  {C.DIM}note: firmware probe was incomplete; commands may surface real errors.{C.RESET}")
        return 0

    device_name = args.device

    spinner = None if json_out else Spinner(f"Resolving {device_name}.local")
    if spinner:
        spinner.start()

    hostname = f"{device_name}.local"
    try:
        ip = await resolve_mdns(hostname)
        if spinner:
            spinner.stop(success=True)
    except RuntimeError:
        if json_out:
            return fail(
                "device_not_found",
                f"Could not resolve {device_name}.local",
                retryable=True,
                next_action="Confirm the device is powered on and on the same network, then run truffile scan --json",
            )
        assert spinner is not None
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
        spinner = None if json_out else Spinner("Validating existing token")
        if spinner:
            spinner.start()
        client = TruffleClient(address, existing_token)
        try:
            await client.connect()
            if await client.check_auth():
                if spinner:
                    spinner.stop(success=True)
                storage.set_last_used(device_name)
                if json_out:
                    emit_json(ok_payload(
                        state="paired",
                        device=device_name,
                        address=address,
                        reused_session=True,
                    ))
                    return 0
                success(f"Already connected to {C.BOLD}{device_name}{C.RESET}")
                return 0
            if spinner:
                spinner.fail("Token invalid, re-authenticating")
        except Exception:
            if spinner:
                spinner.fail("Token validation failed")
        finally:
            await client.close()

    user_id = (getattr(args, "user_id", None) or "").strip()
    stored_uid = (storage.state.client_user_id or "").strip()

    if not user_id:
        if non_interactive:
            return fail(
                "user_id_required",
                "A Symphony User ID is required to connect",
                next_action=f"Get the User ID from Symphony Settings, then run truffile connect {device_name} --user-id <user-id> --json",
            )
        print()
        print(f"  {C.DIM}Make sure you have:{C.RESET}")
        print(f"  {C.DIM}{DOT} Onboarded with the Truffle app{C.RESET}")
        print(f"  {C.DIM}{DOT} Your User ID from Symphony Settings{C.RESET}")
        print()
        try:
            default_hint = f" [{stored_uid}]" if stored_uid else ""
            entered = input(f"{C.CYAN}?{C.RESET} Enter your User ID{default_hint}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            raise KeyboardInterrupt()
        user_id = entered or stored_uid

    if not user_id:
        return fail(
            "user_id_required",
            "A Symphony User ID is required to connect",
            next_action=f"Get the User ID from Symphony Settings, then run truffile connect {device_name} --user-id <user-id>",
        )

    # persist for future runs and onboarding default
    if user_id != stored_uid:
        storage.state.client_user_id = user_id
        storage.save()

    spinner = None if json_out else Spinner("Connecting to device")
    if spinner:
        spinner.start()

    client = TruffleClient(address, token="")
    try:
        await client.connect()
        if spinner:
            spinner.stop(success=True)
    except Exception as e:
        if spinner:
            spinner.fail(f"Failed to connect: {e}")
        await client.close()
        return fail("connection_failed", f"Failed to connect: {e}", retryable=True)

    if not json_out:
        print()
        info("Requesting authorization...")
        print(f"  {C.DIM}Please approve on your Truffle device{C.RESET}")

    spinner = None if json_out else Spinner("Waiting for approval")
    if spinner:
        spinner.start()

    try:
        registration = client.register_new_session(user_id)
        if approval_timeout is None:
            status, token = await registration
        else:
            status, token = await asyncio.wait_for(
                registration,
                timeout=float(approval_timeout),
            )
    except asyncio.TimeoutError:
        if spinner:
            spinner.fail("Approval timed out")
        await client.close()
        return fail(
            "approval_timeout",
            "Timed out waiting for approval on the Truffle device",
            retryable=True,
            next_action="Run connect again and approve the new session on the Truffle device",
        )
    except Exception as e:
        if spinner:
            spinner.fail(f"Failed to register: {e}")
        await client.close()
        return fail("registration_failed", f"Failed to register: {e}", retryable=True)

    await client.close()

    if status.error == NewSessionStatus.NEW_SESSION_SUCCESS and token:
        if spinner:
            spinner.stop(success=True)
        storage.set_token(device_name, token)
        storage.set_last_used(device_name)
        if json_out:
            emit_json(ok_payload(
                state="paired",
                device=device_name,
                address=address,
                reused_session=False,
            ))
            return 0
        print()
        success(f"Connected to {C.BOLD}{device_name}{C.RESET}")
        return 0
    elif status.error == NewSessionStatus.NEW_SESSION_TIMEOUT:
        if spinner:
            spinner.fail("Approval timed out")
        return fail(
            "approval_timeout",
            "Approval timed out",
            retryable=True,
            next_action="Run connect again and approve the new session on the Truffle device",
        )
    elif status.error == NewSessionStatus.NEW_SESSION_REJECTED:
        if spinner:
            spinner.fail("Request was rejected")
        return fail("approval_rejected", "The connection request was rejected on the Truffle device")
    else:
        if spinner:
            spinner.fail(f"Authentication failed: {status.error}")
        return fail("authentication_failed", f"Authentication failed: {status.error}")


def cmd_disconnect(args, storage: StorageService) -> int:
    json_out = bool(getattr(args, "json", False))
    # In-container: the session token is provided by the runtime, not by us.
    # We can't revoke it from here, so disconnect is a no-op.
    if probe_in_container_device() is not None:
        if json_out:
            emit_json(ok_payload(
                state="unchanged",
                execution_context="truffle_container",
                message="The runtime owns the in-container session",
            ))
            return 0
        info("disconnect is a no-op inside a Truffle app container")
        print(f"  {C.DIM}the session token comes from the runtime and lives for the container lifetime.{C.RESET}")
        return 0

    target = getattr(args, "device", "all")
    if target == "all":
        removed = storage.list_devices()
        storage.clear_all()
        if json_out:
            emit_json(ok_payload(disconnected=removed))
            return 0
        success("All device credentials cleared")
    else:
        if storage.remove_device(target):
            if json_out:
                emit_json(ok_payload(disconnected=[target]))
                return 0
            success(f"Disconnected from {C.BOLD}{target}{C.RESET}")
        else:
            if json_out:
                return emit_error("device_not_found", f"No credentials found for {target}", device=target)
            error(f"No credentials found for {target}")
            return 1
    return 0


async def cmd_scan(args, storage: StorageService) -> int:
    json_out = bool(getattr(args, "json", False))
    non_interactive = bool(getattr(args, "non_interactive", False)) or json_out
    timeout = int(getattr(args, "timeout", 5))
    if timeout <= 0:
        if json_out:
            return emit_error("invalid_args", "--timeout must be greater than zero")
        error("--timeout must be greater than zero")
        return 1

    # In-container short-circuit: the host firmware is the only "device" we
    # can possibly reach from inside a CNI-isolated app container, and we
    # already know how to reach it. Skip mDNS entirely.
    ic_info = probe_in_container_device()
    if ic_info is not None:
        if json_out:
            emit_json(ok_payload(
                execution_context="truffle_container",
                devices=[{
                    "name": ic_info.device_name,
                    "addresses": [ic_info.ip_address] if ic_info.ip_address else [],
                    "port": 80,
                    "connected": True,
                    "grpc_address": ic_info.grpc_address,
                    "firmware_version": ic_info.firmware_version or None,
                }],
            ))
            return 0
        print(f"{C.DIM}[in-container mode] skipping mDNS scan{C.RESET}")
        print()
        print(f"{C.BOLD}DEVICES{C.RESET}")
        print(f"{C.DIM}-------{C.RESET}")
        marker = "(this device)"
        print(f"  {C.GREEN}*{C.RESET} {C.BOLD}{ic_info.device_name}{C.RESET}    {C.DIM}{marker}{C.RESET}")
        if ic_info.serial:
            print(f"      {C.DIM}serial:{C.RESET}    {ic_info.serial}")
        if ic_info.ip_address:
            print(f"      {C.DIM}ip:{C.RESET}        {ic_info.ip_address}")
        if ic_info.mac_address:
            print(f"      {C.DIM}mac:{C.RESET}       {ic_info.mac_address}")
        if ic_info.firmware_version:
            print(f"      {C.DIM}firmware:{C.RESET}  {ic_info.firmware_version}")
        if ic_info.timezone:
            print(f"      {C.DIM}timezone:{C.RESET}  {ic_info.timezone}")
        print(f"      {C.DIM}via:{C.RESET}       in-container short-circuit ({ic_info.grpc_address})")
        print()
        print(f"{C.DIM}auth:       APP_SESSION_TOKEN (installing-user session){C.RESET}")
        print(f"{C.DIM}transport:  native gRPC -> envoy :80 -> firmware UDS @tfw-core{C.RESET}")
        print(f"{C.DIM}discovery:  none (already connected){C.RESET}")
        if ic_info.probe_failed:
            print()
            print(f"  {C.DIM}note: firmware probe was incomplete; some fields may be missing.{C.RESET}")
        print()
        return 0

    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf, IPVersion
    except ImportError:
        if json_out:
            return emit_error(
                "dependency_missing",
                "zeroconf package required for scanning",
                next_action="pip install zeroconf",
            )
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

    spinner = None if json_out else Spinner(f"Scanning for Truffle devices ({timeout}s)")
    if spinner:
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
        if spinner:
            spinner.fail(f"Scan failed: {e}")
        if json_out:
            return emit_error("scan_failed", f"Scan failed: {e}", retryable=True)
        return 1

    if spinner:
        spinner.stop(success=True)

    if not devices:
        if json_out:
            return emit_error(
                "device_not_found",
                "No Truffle devices found on the network",
                retryable=True,
                devices=[],
                next_action="Confirm the Truffle is powered on and connected to the same network",
            )
        print()
        print(f"  {C.DIM}No Truffle devices found on the network{C.RESET}")
        print()
        print(f"  {C.DIM}Make sure your Truffle is:{C.RESET}")
        print(f"    {C.DIM}• Powered on{C.RESET}")
        print(f"    {C.DIM}• Connected to the same network as this computer{C.RESET}")
        print()
        return 1

    device_list = sorted(devices.values(), key=lambda item: item["name"])
    for device in device_list:
        device["connected"] = storage.get_token(device["name"]) is not None

    if json_out:
        emit_json(ok_payload(devices=device_list))
        return 0

    print()
    print(f"{C.BOLD}Found {len(devices)} Truffle device(s):{C.RESET}")
    print()

    for i, device in enumerate(device_list, 1):
        name = device["name"]
        addrs = ", ".join(device["addresses"]) if device["addresses"] else "unknown"

        already_connected = bool(device["connected"])
        if already_connected:
            print(f"  {C.GREEN}{i}.{C.RESET} {C.BOLD}{name}{C.RESET} {C.DIM}({addrs}){C.RESET} {C.GREEN}[connected]{C.RESET}")
        else:
            print(f"  {C.CYAN}{i}.{C.RESET} {C.BOLD}{name}{C.RESET} {C.DIM}({addrs}){C.RESET}")

    print()

    if non_interactive:
        return 0

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


async def _resolve_connected_device(
    storage: StorageService,
    *,
    quiet: bool = False,
) -> tuple[str, str] | tuple[None, None]:
    # In-container short-circuit: skip mDNS, return the env-provided host
    # for the synthetic device that the CLI startup injected into storage.
    ic_info = getattr(storage, "_in_container_info", None)
    if ic_info is not None:
        return ic_info.device_name, ic_info.host

    device = storage.state.last_used_device
    if not device:
        if not quiet:
            error("No device connected")
            print(f"  {C.DIM}Run: truffile connect <device>{C.RESET}")
        return None, None
    try:
        ip = await resolve_mdns(f"{device}.local")
    except RuntimeError:
        if not quiet:
            error(f"Could not resolve {device}.local")
        return None, None
    return device, ip
