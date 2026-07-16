import sys
from typing import Any

import httpx

from truffile.storage import StorageService
from truffile.client import resolve_mdns

from .connect import _resolve_connected_device
from .in_container import in_container_http_headers
from .output import emit_error, emit_json, exception_details, ok_payload
from .ui import C, CHECK, MUSHROOM, WARN, Spinner, error, warn

try:
    import termios
    import tty
except Exception:
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]


async def cmd_models(args, storage: StorageService) -> int:
    """List models on your Truffle."""
    json_out = bool(getattr(args, "json", False))
    timeout = float(getattr(args, "timeout", 15.0) or 15.0)
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

    spinner = None if json_out else Spinner(f"Connecting to {device}")
    if spinner:
        spinner.start()

    try:
        url = f"http://{ip}/if2/v1/models"
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=in_container_http_headers())
            resp.raise_for_status()
            payload = resp.json()
        if spinner:
            spinner.stop(success=True)
    except Exception as e:
        if spinner:
            spinner.fail(f"Failed to get IF2 models: {e}")
        if json_out:
            details = exception_details(e, default_code="model_list_failed")
            return emit_error(
                details.pop("code"),
                details.pop("message"),
                service="if2",
                device=device,
                **details,
            )
        return 1

    models = payload.get("data", [])
    if not isinstance(models, list):
        if spinner:
            spinner.fail("Invalid response: missing 'data' list")
        if json_out:
            return emit_error("invalid_response", "Invalid response: missing 'data' list", service="if2")
        return 1

    if json_out:
        emit_json(ok_payload(device=device, service="if2", models=models))
        return 0

    print()
    print(f"{MUSHROOM} {C.BOLD}IF2 Models on {device}{C.RESET}")
    print()

    if not models:
        print(f"  {C.DIM}No models found{C.RESET}")
        return 0

    for m in models:
        if not isinstance(m, dict):
            continue
        model_id = m.get("id", "<unknown>")
        name = m.get("name", model_id)
        uuid = m.get("uuid", "<none>")
        ctx = m.get("context_length", "<unknown>")
        arch = m.get("architecture", {})
        tokenizer = arch.get("tokenizer", "<unknown>") if isinstance(arch, dict) else "<unknown>"
        max_batch = m.get("max_batch_size", "<unknown>")
        print(f"  {C.GREEN}{CHECK}{C.RESET} {name}")
        print(f"    {C.DIM}id: {model_id}{C.RESET}")
        print(f"    {C.DIM}uuid: {uuid}{C.RESET}")
        print(f"    {C.DIM}context: {ctx}, tokenizer: {tokenizer}, max_batch: {max_batch}{C.RESET}")

    return 0


async def _default_model(ip: str) -> str | None:
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"http://{ip}/if2/v1/models", headers=in_container_http_headers())
            resp.raise_for_status()
            payload = resp.json()
        models = payload.get("data", [])
        if not isinstance(models, list) or not models:
            return None
        default = _pick_default_model(models)
        if default is None:
            return None
        return str(default.get("id") or default.get("uuid") or "")
    except Exception:
        return None


def _pick_default_model(models: list[dict[str, Any]]) -> dict[str, Any] | None:
    usable = [m for m in models if isinstance(m, dict)]
    if not usable:
        return None

    def _normalized_text(model: dict[str, Any]) -> str:
        raw = " ".join(
            str(model.get(key) or "")
            for key in ("name", "id", "uuid")
        ).lower()
        return "".join(ch for ch in raw if ch.isalnum())

    preferred_matches = [
        model
        for model in usable
        if "qwen" in _normalized_text(model) and "35b" in _normalized_text(model)
    ]
    if preferred_matches:
        preferred_matches.sort(key=lambda m: str(m.get("name") or m.get("id") or m.get("uuid") or ""))
        return preferred_matches[0]

    usable.sort(key=lambda m: str(m.get("name") or m.get("id") or m.get("uuid") or ""))
    return usable[0]


def _model_display_name(model: dict[str, Any]) -> str:
    model_id = str(model.get("id") or "<unknown>")
    name = str(model.get("name") or model_id)
    if name == model_id:
        return name
    return f"{name} ({model_id})"


def _model_value(model: dict[str, Any]) -> str:
    return str(model.get("uuid") or model.get("id") or "")


def _model_matches_current(model: dict[str, Any], current_model: str) -> bool:
    if not current_model:
        return False
    mv = _model_value(model)
    mid = str(model.get("id") or "")
    return current_model in {mv, mid}


def _pick_model_with_numbers(models: list[dict[str, Any]], current_model: str) -> str | None:
    if not models:
        return None
    print(f"{C.BLUE}models:{C.RESET}")
    default_idx = 0
    for i, m in enumerate(models, start=1):
        active = f" {C.DIM}[active]{C.RESET}" if _model_matches_current(m, current_model) else ""
        if active:
            default_idx = i - 1
        print(f"{C.BLUE}{i}.{C.RESET} {_model_display_name(m)}{active}")
    choice = input(f"{C.CYAN}?{C.RESET} select model [1-{len(models)}] (Enter to keep): ").strip()
    if not choice:
        return _model_value(models[default_idx])
    try:
        idx = int(choice) - 1
    except ValueError:
        warn("invalid model selection")
        return None
    if idx < 0 or idx >= len(models):
        warn("invalid model selection")
        return None
    return _model_value(models[idx])


def _pick_model_interactive(models: list[dict[str, Any]], current_model: str) -> str | None:
    if not models:
        return None
    if not sys.stdin.isatty() or not sys.stdout.isatty() or termios is None or tty is None:
        return _pick_model_with_numbers(models, current_model)

    selected = 0
    for i, m in enumerate(models):
        if _model_matches_current(m, current_model):
            selected = i
            break

    lines_rendered = 0

    def _render() -> None:
        nonlocal lines_rendered
        lines: list[str] = []
        lines.append(f"{C.BLUE}select model (↑/↓, Enter=select, q=cancel){C.RESET}")
        for i, m in enumerate(models):
            pointer = "›" if i == selected else " "
            active = f" {C.DIM}[active]{C.RESET}" if _model_matches_current(m, current_model) else ""
            line = f" {C.CYAN}{pointer}{C.RESET} {_model_display_name(m)}{active}"
            lines.append(line)

        if lines_rendered > 0:
            sys.stdout.write(f"\033[{lines_rendered}A")
        for line in lines:
            sys.stdout.write(f"\r\033[K{line}\n")
        sys.stdout.flush()
        lines_rendered = len(lines)

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        _render()
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                sys.stdout.write("\r\033[K")
                return _model_value(models[selected])
            if ch in ("q", "Q"):
                sys.stdout.write("\r\033[K")
                return None
            if ch == "\x1b":
                seq1 = sys.stdin.read(1)
                if seq1 == "[":
                    seq2 = sys.stdin.read(1)
                    if seq2 == "A":
                        selected = (selected - 1) % len(models)
                        _render()
                        continue
                    if seq2 == "B":
                        selected = (selected + 1) % len(models)
                        _render()
                        continue
                return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        if lines_rendered > 0:
            sys.stdout.write(f"\033[{lines_rendered}A")
            for _ in range(lines_rendered):
                sys.stdout.write("\r\033[K\n")
            sys.stdout.write(f"\033[{lines_rendered}A")
        sys.stdout.flush()


def _fetch_models_payload(client: httpx.Client, ip: str) -> list[dict[str, Any]]:
    resp = client.get(f"http://{ip}/if2/v1/models", headers=in_container_http_headers(), timeout=15.0)
    resp.raise_for_status()
    payload = resp.json()
    raw = payload.get("data", [])
    if not isinstance(raw, list):
        raise RuntimeError("invalid models payload")
    out: list[dict[str, Any]] = []
    for m in raw:
        if isinstance(m, dict):
            out.append(m)
    try:
        out.sort(key=lambda m: str(m.get("name") or m.get("id") or m.get("uuid") or ""))
    except Exception:        pass

    return out
