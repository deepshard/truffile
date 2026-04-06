import os
import select
import sys
import threading
import time
from pathlib import Path
from typing import Any

try:
    import termios
    import tty
except Exception:
    termios = None
    tty = None


class C:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


MUSHROOM = "🍄‍🟫"
CHECK = "✓"
CROSS = "✗"
ARROW = "→"
DOT = "•"
WARN = "⚠"
HAMMER = "🔨"
SUPPORTED_SERVER_MIME_TYPES = {"image/jpeg", "image/png", "image/bmp"}
SCAFFOLD_ICON_RESOURCE_REL = Path("assets") / "Truffle.png"


class Spinner:
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str):
        self.message = message
        self.running = False
        self.thread = None
        self.frame_idx = 0

    def _spin(self):
        while self.running:
            frame = self.FRAMES[self.frame_idx % len(self.FRAMES)]
            sys.stdout.write(f"\r{C.CYAN}{frame}{C.RESET} {self.message}")
            sys.stdout.flush()
            self.frame_idx += 1
            time.sleep(0.08)

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self, success: bool = True):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        icon = f"{C.GREEN}{CHECK}{C.RESET}" if success else f"{C.RED}{CROSS}{C.RESET}"
        sys.stdout.write(f"\r{icon} {self.message}\n")
        sys.stdout.flush()

    def fail(self, message: str | None = None):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        msg = message or self.message
        sys.stdout.write(f"\r{C.RED}{CROSS}{C.RESET} {msg}\n")
        sys.stdout.flush()


def create_thinking_orb():
    from .art import ParticleOrb
    return ParticleOrb(num_particles=5)


class ScrollingLog:
    def __init__(self, height: int = 6, prefix: str = "  "):
        self.height = height
        self.prefix = prefix
        self.lines: list[str] = []
        self.started = False
        try:
            import shutil
            self.width = shutil.get_terminal_size().columns - len(prefix) - 2
        except Exception:
            self.width = 76

    def _truncate(self, line: str) -> str:
        if len(line) > self.width:
            return line[:self.width - 3] + "..."
        return line

    def _render(self):
        if self.started:
            sys.stdout.write(f"\033[{self.height}A")
        display = self.lines[-self.height:] if len(self.lines) >= self.height else self.lines
        while len(display) < self.height:
            display.insert(0, "")
        for line in display:
            truncated = self._truncate(line)
            sys.stdout.write(f"\033[K{self.prefix}{C.DIM}{truncated}{C.RESET}\n")
        sys.stdout.flush()
        self.started = True

    def add(self, line: str):
        self.lines.append(line.rstrip())
        self._render()

    def finish(self):
        if self.started:
            sys.stdout.write(f"\033[{self.height}A")
            for _ in range(self.height):
                sys.stdout.write("\033[K\n")
            sys.stdout.write(f"\033[{self.height}A")
            sys.stdout.flush()


class StreamAbortWatcher:
    """Watches for ESC key during streaming. Use as context manager."""

    def __init__(self) -> None:
        self.enabled = bool(sys.stdin.isatty() and termios is not None and tty is not None)
        self._fd: int | None = None
        self._old_attrs: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._aborted = False

    def __enter__(self) -> "StreamAbortWatcher":
        if not self.enabled:
            return self
        try:
            self._fd = sys.stdin.fileno()
            self._old_attrs = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        except Exception:
            self.enabled = False
            return self
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()
        return self

    def _watch(self) -> None:
        if self._fd is None:
            return
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([self._fd], [], [], 0.1)
            except Exception:
                return
            if not ready:
                continue
            try:
                ch = os.read(self._fd, 1)
            except Exception:
                continue
            if ch == b"\x1b":
                self._aborted = True
                self._stop.set()
                return

    def aborted(self) -> bool:
        return self._aborted

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.2)
        if self.enabled and self._fd is not None and self._old_attrs is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)
            except Exception:
                pass
        return False


def error(msg: str):
    print(f"{C.RED}{CROSS} Error:{C.RESET} {msg}")


def warn(msg: str):
    print(f"{C.YELLOW}{WARN} Warning:{C.RESET} {msg}")


def success(msg: str):
    print(f"{C.GREEN}{CHECK}{C.RESET} {msg}")


def info(msg: str):
    print(f"{C.CYAN}{DOT}{C.RESET} {msg}")


def print_help():
    print(f"""
{C.BOLD}Usage:{C.RESET} truffile <command> [options]

{C.BOLD}Commands:{C.RESET}
  {C.CYAN}scan{C.RESET}                    scan for truffle devices on the network
  {C.CYAN}connect{C.RESET} <device>         connect to a truffle device
  {C.CYAN}disconnect{C.RESET} [device|all]  disconnect from device(s)
  {C.CYAN}create{C.RESET} [name]            scaffold a new app
  {C.CYAN}validate{C.RESET} [path]          validate app directory
  {C.CYAN}deploy{C.RESET} [path]            deploy app to connected device
  {C.CYAN}list{C.RESET} <apps|devices>      list installed apps or connected devices
  {C.CYAN}delete{C.RESET} [app]             delete app from device
  {C.CYAN}models{C.RESET}                   list inference models on device
  {C.CYAN}chat{C.RESET}                     interactive chat with device
  {C.CYAN}help{C.RESET}                     show this help

{C.BOLD}Examples:{C.RESET}
  truffile scan
  truffile connect truffle-1234
  truffile create my-app
  truffile deploy ./my-app
  truffile list apps
  truffile chat
""")
