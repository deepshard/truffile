import sys
from typing import Any

import httpx

from truffile.storage import StorageService
from truffile.client import resolve_mdns

from .ui import C, CHECK, MUSHROOM, WARN, Spinner, error, warn

try:
    import termios
    import tty
except Exception:
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]


async def cmd_models(storage: StorageService) -> int:
    """List models on your Truffle."""
    device = storage.state.last_used_device
    if not device:
        error("No device connected")
        print(f"  {C.DIM}Run: truffile connect <device>{C.RESET}")
        return 1

    spinner = Spinner(f"Connecting to {device}")
    spinner.start()

    try:
        ip = await resolve_mdns(f"{device}.local")
    except RuntimeError:
        spinner.fail(f"Could not resolve {device}.local")
        return 1

    try:
        url = f"http://{ip}/if2/v1/models"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
        spinner.stop(success=True)
    except Exception as e:
        spinner.fail(f"Failed to get IF2 models: {e}")
        return 1

    models = payload.get("data", [])
    if not isinstance(models, list):
        spinner.fail("Invalid response: missing 'data' list")
        return 1

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
            resp = client.get(f"http://{ip}/if2/v1/models")
            resp.raise_for_status()
            payload = resp.json()
        models = payload.get("data", [])
        if not isinstance(models, list) or not models:
            return None
        # sort models by name/id so default is 35b typically & list is consistent
        models.sort(key=lambda m: str(m.get("name") or m.get("id") or m.get("uuid") or ""))
        first = models[0]
        return str(first.get("id") or first.get("uuid") or "")
    except Exception:
        return None


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
    resp = client.get(f"http://{ip}/if2/v1/models", timeout=15.0)
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
