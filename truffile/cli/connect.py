import asyncio

from truffile.storage import StorageService
from truffile.client import TruffleClient, resolve_mdns, NewSessionStatus

from .ui import C, DOT, Spinner, error, success, info


async def cmd_connect(args, storage: StorageService) -> int:
    device_name = args.device

    spinner = Spinner(f"Resolving {device_name}.local")
    spinner.start()

    hostname = f"{device_name}.local"
    try:
        ip = await resolve_mdns(hostname)
        spinner.stop(success=True)
    except RuntimeError:
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
        spinner = Spinner("Validating existing token")
        spinner.start()
        client = TruffleClient(address, existing_token)
        try:
            await client.connect()
            if await client.check_auth():
                spinner.stop(success=True)
                storage.set_last_used(device_name)
                success(f"Already connected to {C.BOLD}{device_name}{C.RESET}")
                await client.close()
                return 0
            spinner.fail("Token invalid, re-authenticating")
        except Exception:
            spinner.fail("Token validation failed")
        finally:
            await client.close()

    print()
    print(f"  {C.DIM}Make sure you have:{C.RESET}")
    print(f"  {C.DIM}{DOT} Onboarded with the Truffle app{C.RESET}")
    print(f"  {C.DIM}{DOT} Your User ID from the recovery codes{C.RESET}")
    print()

    try:
        user_id = input(f"{C.CYAN}?{C.RESET} Enter your User ID: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        raise KeyboardInterrupt()
    if not user_id:
        error("User ID is required")
        return 1

    spinner = Spinner("Connecting to device")
    spinner.start()

    client = TruffleClient(address, token="")
    try:
        await client.connect()
        spinner.stop(success=True)
    except Exception as e:
        spinner.fail(f"Failed to connect: {e}")
        return 1

    print()
    info("Requesting authorization...")
    print(f"  {C.DIM}Please approve on your Truffle device{C.RESET}")

    spinner = Spinner("Waiting for approval")
    spinner.start()

    try:
        status, token = await client.register_new_session(user_id)
    except Exception as e:
        spinner.fail(f"Failed to register: {e}")
        await client.close()
        return 1

    await client.close()

    if status.error == NewSessionStatus.NEW_SESSION_SUCCESS and token:
        spinner.stop(success=True)
        storage.set_token(device_name, token)
        storage.set_last_used(device_name)
        print()
        success(f"Connected to {C.BOLD}{device_name}{C.RESET}")
        return 0
    elif status.error == NewSessionStatus.NEW_SESSION_TIMEOUT:
        spinner.fail("Approval timed out")
        return 1
    elif status.error == NewSessionStatus.NEW_SESSION_REJECTED:
        spinner.fail("Request was rejected")
        return 1
    else:
        spinner.fail(f"Authentication failed: {status.error}")
        return 1


def cmd_disconnect(args, storage: StorageService) -> int:
    target = args.target
    if target == "all":
        storage.clear_all()
        success("All device credentials cleared")
    else:
        if storage.remove_device(target):
            success(f"Disconnected from {C.BOLD}{target}{C.RESET}")
        else:
            error(f"No credentials found for {target}")
    return 0


async def cmd_scan(args, storage: StorageService) -> int:
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf, IPVersion
    except ImportError:
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

    timeout = args.timeout if hasattr(args, 'timeout') else 5

    spinner = Spinner(f"Scanning for Truffle devices ({timeout}s)")
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
        spinner.fail(f"Scan failed: {e}")
        return 1

    spinner.stop(success=True)

    if not devices:
        print()
        print(f"  {C.DIM}No Truffle devices found on the network{C.RESET}")
        print()
        print(f"  {C.DIM}Make sure your Truffle is:{C.RESET}")
        print(f"    {C.DIM}• Powered on{C.RESET}")
        print(f"    {C.DIM}• Connected to the same network as this computer{C.RESET}")
        print()
        return 1

    print()
    print(f"{C.BOLD}Found {len(devices)} Truffle device(s):{C.RESET}")
    print()

    device_list = list(devices.values())
    for i, device in enumerate(device_list, 1):
        name = device["name"]
        addrs = ", ".join(device["addresses"]) if device["addresses"] else "unknown"

        already_connected = storage.get_token(name) is not None
        if already_connected:
            print(f"  {C.GREEN}{i}.{C.RESET} {C.BOLD}{name}{C.RESET} {C.DIM}({addrs}){C.RESET} {C.GREEN}[connected]{C.RESET}")
        else:
            print(f"  {C.CYAN}{i}.{C.RESET} {C.BOLD}{name}{C.RESET} {C.DIM}({addrs}){C.RESET}")

    print()

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


async def _resolve_connected_device(storage: StorageService) -> tuple[str, str] | tuple[None, None]:
    device = storage.state.last_used_device
    if not device:
        error("No device connected")
        print(f"  {C.DIM}Run: truffile connect <device>{C.RESET}")
        return None, None
    try:
        ip = await resolve_mdns(f"{device}.local")
    except RuntimeError:
        error(f"Could not resolve {device}.local")
        return None, None
    return device, ip
