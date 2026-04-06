from __future__ import annotations

import math
import os
import sys
import threading
import time

try:
    import termios
    import tty
except Exception:
    termios = None
    tty = None

# truffle shape — bean/mushroom cap outline
# using block characters for solid fills and edges

TRUFFLE_BANNER = [
    "##########@@%**+++====+++**%@@##########",
    "######%+=-::-===++++++++===-::-=+%######",
    "####+::-+%@##################@%+-::+####",
    "##%:.+@##########################@+.:%##",
    "#%..@##############################@. %#",
    "#: %################################% :#",
    "# .##################################. #",
    "#. ################################## .#",
    "#= +################################= +#",
    "##- =@##########@@%%%@@###########@= =##",
    "###*-.-=++++===-::----::-==+++++=-.-*###",
    "#####@*+====++*%@#####@@%*++====+*@#####",
]

TRUFFLE_BANNER_BRAILLE = [
    "⠀⠀⠀⠀⠀⠀⠀⣀⣀⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣀⣀⠀⠀⠀⠀⠀⠀⠀",
    "⠀⠀⠀⢀⣤⣶⠿⠛⠋⠉⠉⠁⠀⠀⠀⠀⠀⠈⠉⠉⠙⠛⠿⣶⣤⡀⠀⠀⠀",
    "⠀⠀⣴⡿⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⢿⣦⠀⠀",
    "⠀⣼⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⣧⠀",
    "⢠⣿⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣿⡄",
    "⠘⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣿⠃",
    "⠀⢿⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⡟⠀",
    "⠀⠈⠻⣷⣄⡀⠀⠀⠀⣀⣀⣠⣤⣤⣤⣤⣤⣄⣀⡀⠀⠀⠀⢀⣠⣾⠟⠁⠀",
    "⠀⠀⠀⠈⠙⠛⠿⠿⠟⠛⠛⠉⠉⠁⠀⠈⠉⠙⠛⠛⠻⠿⠿⠛⠋⠁⠀⠀⠀",
]

ORB = [
    "⢀⣶⣶⡀",
    "⢸⣿⣿⡇",
    "⠈⠿⠿⠁",
]

# color stops
PINK = (255, 105, 180)
HOT_PINK = (255, 20, 147)
BLUE = (100, 149, 237)
ROYAL_BLUE = (65, 105, 225)
ORANGE = (255, 165, 0)
CYAN = (0, 255, 255)


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _supports_truecolor() -> bool:
    ct = os.environ.get("COLORTERM", "").lower()
    if ct in ("truecolor", "24bit"):
        return True
    term = os.environ.get("TERM_PROGRAM", "").lower()
    # terminals known to support truecolor
    if term in ("iterm.app", "hyper", "wezterm", "vscode", "ghostty", "alacritty"):
        return True
    return False


_TRUECOLOR = _supports_truecolor()


def _fg(r: int, g: int, b: int) -> str:
    if _TRUECOLOR:
        return f"\x1b[38;2;{r};{g};{b}m"
    # fallback: use closest ANSI 256 color
    return f"\x1b[38;5;{_rgb_to_256(r, g, b)}m"


def _rgb_to_256(r: int, g: int, b: int) -> int:
    """Map RGB to nearest xterm-256 color cube index."""
    # check if close to grayscale
    if r == g == b:
        if r < 8:
            return 16
        if r > 248:
            return 231
        return round((r - 8) / 247 * 24) + 232
    # map to 6x6x6 color cube
    ri = round(r / 255 * 5)
    gi = round(g / 255 * 5)
    bi = round(b / 255 * 5)
    return 16 + 36 * ri + 6 * gi + bi


RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"


def _terminal_width() -> int:
    try:
        import shutil
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def _center(line: str, width: int) -> str:
    # braille chars are all width 1 visually
    visible = len(line)
    pad = max(0, (width - visible) // 2)
    return " " * pad + line


def _color_top_row(line: str, phase: float = 0.0) -> str:
    out = ""
    stroke_positions = [i for i, ch in enumerate(line) if ch != BRAILLE_BLANK and ch != " "]
    total = len(stroke_positions)
    for i, ch in enumerate(line):
        if ch == BRAILLE_BLANK or ch == " ":
            out += RESET + ch
        else:
            idx = stroke_positions.index(i)
            # mix pink and blue based on position + phase offset
            t = (idx / max(total - 1, 1) + phase) % 1.0
            # use sine to blend so both colors are always present
            blend = (math.sin(t * math.pi * 3) + 1.0) / 2.0
            c = _lerp(HOT_PINK, ROYAL_BLUE, blend)
            out += _fg(*c) + ch
    return out + RESET


def render_banner(*, fade_in: bool = True) -> None:
    lines = TRUFFLE_BANNER_BRAILLE
    label = f"{_fg(*ROYAL_BLUE)}{BOLD}Truffile{RESET} {DIM}— Truffle SDK{RESET}"
    banner_width = len(lines[0])
    # put label to the right of the middle row
    label_row = len(lines) // 2

    for i, line in enumerate(lines):
        if i <= 1:
            row = _color_top_row(line)
        else:
            row = line
        if i == label_row:
            row += "  " + label
        print(row)
        if fade_in:
            time.sleep(0.04)

    print()


BRAILLE_BLANK = "⠀"


def _color_strokes(line: str, color: tuple[int, int, int]) -> str:
    out = ""
    c = _fg(*color)
    for ch in line:
        if ch == BRAILLE_BLANK or ch == " ":
            out += RESET + ch
        else:
            out += c + ch
    return out + RESET


def render_small(*, color: tuple[int, int, int] = PINK) -> str:
    result = ""
    for line in TRUFFLE_SMALL:
        result += _color_strokes(line, color) + "\n"
    return result


class GlowBanner:
    """Renders banner then keeps top rows glowing in a background thread."""

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._row0: int = 0  # absolute terminal row of banner line 0

    @staticmethod
    def _query_cursor_row() -> int | None:
        """Query current cursor row via DSR escape sequence."""
        import select
        try:
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd) if termios else None
            if tty:
                tty.setcbreak(fd)
            sys.stdout.write("\x1b[6n")
            sys.stdout.flush()
            ready, _, _ = select.select([fd], [], [], 0.1)
            if not ready:
                if old and termios:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
                return None
            resp = b""
            while True:
                ready, _, _ = select.select([fd], [], [], 0.05)
                if not ready:
                    break
                ch = os.read(fd, 1)
                resp += ch
                if ch == b"R":
                    break
            if old and termios:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            # response: \x1b[row;colR
            decoded = resp.decode("ascii", errors="ignore")
            if "[" in decoded and ";" in decoded:
                row_str = decoded.split("[")[1].split(";")[0]
                return int(row_str)
        except Exception:
            pass
        return None

    def start(self) -> None:
        """Print the banner and start the glow loop."""
        lines = TRUFFLE_BANNER_BRAILLE
        label = f"{_fg(*ROYAL_BLUE)}{BOLD}Truffile{RESET} {DIM}— Truffle SDK{RESET}"
        label_row = len(lines) // 2

        # query cursor row before printing to know where banner starts
        row_before = self._query_cursor_row() if sys.stdout.isatty() else None

        for i, line in enumerate(lines):
            if i <= 1:
                row = _color_top_row(line)
            else:
                row = line
            if i == label_row:
                row += "  " + label
            print(row)
        print()

        if not sys.stdout.isatty() or row_before is None:
            return

        self._row0 = row_before  # absolute row where line 0 of banner is
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        lines = TRUFFLE_BANNER_BRAILLE
        start = time.monotonic()
        while self._running:
            t = time.monotonic() - start
            phase = t * 0.5
            # use absolute positioning to the exact rows
            sys.stdout.write("\x1b7")
            for i in range(2):
                sys.stdout.write(f"\x1b[{self._row0 + i};1H\x1b[K{_color_top_row(lines[i], phase)}")
            sys.stdout.write("\x1b8")
            sys.stdout.flush()
            time.sleep(0.06)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.3)
            self._thread = None


def render_glow_banner(*, duration: float = 1.5) -> None:
    """Brief glow animation that settles into the static banner with label."""
    lines = TRUFFLE_BANNER_BRAILLE
    height = len(lines)
    label = f"{_fg(*ROYAL_BLUE)}{BOLD}Truffile{RESET} {DIM}— Truffle SDK{RESET}"
    label_row = len(lines) // 2
    start = time.monotonic()

    # print blank lines to make space
    for _ in range(height):
        sys.stdout.write("\n")

    try:
        while time.monotonic() - start < duration:
            elapsed = time.monotonic() - start
            phase = elapsed * 0.8

            sys.stdout.write(f"\x1b[{height}A")
            for i, line in enumerate(lines):
                if i <= 1:
                    row = _color_top_row(line, phase)
                else:
                    row = line
                if i == label_row:
                    row += "  " + label
                sys.stdout.write(f"\x1b[K{row}\n")
            sys.stdout.flush()
            time.sleep(0.04)
    except KeyboardInterrupt:
        pass

    # settle on final static frame
    sys.stdout.write(f"\x1b[{height}A")
    for i, line in enumerate(lines):
        if i <= 1:
            row = _color_top_row(line)
        else:
            row = line
        if i == label_row:
            row += "  " + label
        sys.stdout.write(f"\x1b[K{row}\n")
    sys.stdout.flush()
    print()


def render_glow_demo(*, duration: float = 8.0) -> None:
    import select
    lines = TRUFFLE_BANNER_BRAILLE
    height = len(lines)
    label = f"{_fg(*ROYAL_BLUE)}{BOLD}Truffile{RESET} {DIM}— Truffle SDK{RESET}"
    label_row = len(lines) // 2

    # cbreak mode so any keypress is detected immediately
    old_attrs = None
    if sys.stdin.isatty() and termios and tty:
        try:
            old_attrs = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        except Exception:
            old_attrs = None

    sys.stdout.write("\x1b[?25l")  # hide cursor
    sys.stdout.write("\n")
    for _ in range(height):
        sys.stdout.write("\n")

    start = time.monotonic()
    try:
        while time.monotonic() - start < duration:
            elapsed = time.monotonic() - start
            phase = elapsed * 0.5

            sys.stdout.write(f"\x1b[{height}A")
            for i, line in enumerate(lines):
                if i <= 1:
                    row = _color_top_row(line, phase)
                else:
                    row = line
                if i == label_row:
                    row += "  " + label
                sys.stdout.write(f"\x1b[K{row}\n")
            sys.stdout.flush()

            # check for any keypress — quit on any key
            if old_attrs is not None:
                ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                if ready:
                    os.read(sys.stdin.fileno(), 1024)  # drain
                    break
            else:
                time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        if old_attrs is not None and termios:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_attrs)
        sys.stdout.write("\x1b[?25h")  # show cursor

    # clear the glow area
    sys.stdout.write(f"\x1b[{height}A")
    for _ in range(height):
        sys.stdout.write("\x1b[K\n")
    sys.stdout.write(f"\x1b[{height}A")
    sys.stdout.flush()


class ParticleOrb:
    """particles bouncing inside an invisible circle. pink/blue when active, orange when done."""

    STATE_ACTIVE = "active"
    STATE_DONE = "done"
    STATE_IDLE = "idle"

    # invisible container: 8 dot-wide x 12 dot-tall circle = 4x3 chars
    DOT_W = 8
    DOT_H = 12
    CHAR_W = DOT_W // 2
    CHAR_H = DOT_H // 4
    CX = DOT_W / 2 - 0.5
    CY = DOT_H / 2 - 0.5
    RADIUS = 3.5

    BRAILLE_BASE = 0x2800
    DOT_MAP = [
        (0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (0, 3, 0x40),
        (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20), (1, 3, 0x80),
    ]

    def __init__(self, num_particles: int = 5):
        import random
        self._state = self.STATE_IDLE
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._rng = random.Random()
        # each particle: [orbit_r, speed, phase, wobble_freq, wobble_amp, color_type]
        # color_type: 0=blue, 1=pink
        self._particles: list[list[float]] = []
        self._orange_particles: list[list[float]] = []
        for i in range(num_particles):
            orbit_r = self._rng.uniform(1.0, self.RADIUS * 0.85)
            orbit_speed = self._rng.uniform(0.8, 2.2) * (1 if i % 2 == 0 else -1)
            phase = self._rng.uniform(0, math.pi * 2)
            wobble_freq = self._rng.uniform(1.5, 4.0)
            wobble_amp = self._rng.uniform(0.3, 1.0)
            self._particles.append([orbit_r, orbit_speed, phase, wobble_freq, wobble_amp, float(i % 2)])

    def set_state(self, state: str) -> None:
        with self._lock:
            old = self._state
            self._state = state
            # when switching to done, spawn orange particles among existing ones
            if state == self.STATE_DONE and old != self.STATE_DONE:
                self._orange_particles = []
                for _ in range(3):
                    orbit_r = self._rng.uniform(0.8, self.RADIUS * 0.8)
                    orbit_speed = self._rng.uniform(1.0, 2.5) * self._rng.choice([1, -1])
                    phase = self._rng.uniform(0, math.pi * 2)
                    wobble_freq = self._rng.uniform(2.0, 4.0)
                    wobble_amp = self._rng.uniform(0.3, 0.8)
                    self._orange_particles.append([orbit_r, orbit_speed, phase, wobble_freq, wobble_amp, 2.0])

    def _get_positions(self, t: float) -> list[tuple[float, float, float]]:
        positions = []
        # pink and blue always present
        for p in self._particles:
            orbit_r, speed, phase, wf, wa, color_type = p
            angle = t * speed + phase
            wobble = math.sin(t * wf + phase) * wa
            r = orbit_r + wobble
            r = max(0.3, min(r, self.RADIUS - 0.2))
            x = self.CX + math.cos(angle) * r
            y = self.CY + math.sin(angle) * r * 0.6
            positions.append((x, y, color_type))
        # orange joins when done
        with self._lock:
            if self._state == self.STATE_DONE:
                for p in self._orange_particles:
                    orbit_r, speed, phase, wf, wa, color_type = p
                    angle = t * speed + phase
                    wobble = math.sin(t * wf + phase) * wa
                    r = orbit_r + wobble
                    r = max(0.3, min(r, self.RADIUS - 0.2))
                    x = self.CX + math.cos(angle) * r
                    y = self.CY + math.sin(angle) * r * 0.6
                    positions.append((x, y, color_type))
        return positions

    def _render(self, t: float) -> list[str]:
        with self._lock:
            state = self._state

        positions = self._get_positions(t)
        grid: dict[tuple[int, int], tuple[int, int, int]] = {}
        for x, y, color_type in positions:
            px, py = int(round(x)), int(round(y))
            if 0 <= px < self.DOT_W and 0 <= py < self.DOT_H:
                if color_type > 1.5:
                    grid[(px, py)] = ORANGE
                elif color_type > 0.5:
                    grid[(px, py)] = HOT_PINK
                else:
                    grid[(px, py)] = ROYAL_BLUE

        lines = []
        for cy in range(self.CHAR_H):
            out = ""
            for cx in range(self.CHAR_W):
                code = self.BRAILLE_BASE
                char_color = None
                for dx, dy, bit in self.DOT_MAP:
                    dpx = cx * 2 + dx
                    dpy = cy * 4 + dy
                    if (dpx, dpy) in grid:
                        code |= bit
                        char_color = grid[(dpx, dpy)]
                if char_color and code != self.BRAILLE_BASE:
                    out += _fg(*char_color) + chr(code) + RESET
                else:
                    out += BRAILLE_BLANK
            lines.append(out)
        return lines

    def _draw(self, t: float) -> None:
        try:
            import shutil
            term_h = shutil.get_terminal_size().lines
        except Exception:
            term_h = 24

        rendered = self._render(t)
        sys.stdout.write("\x1b7")
        for i, line in enumerate(rendered):
            row = term_h - self.CHAR_H + i
            sys.stdout.write(f"\x1b[{row};1H\x1b[K{line}")
        sys.stdout.write("\x1b8")
        sys.stdout.flush()

    def _loop(self) -> None:
        start = time.monotonic()
        while self._running:
            t = time.monotonic() - start
            self._draw(t)
            time.sleep(0.06)
        self._clear()

    def _clear(self) -> None:
        try:
            import shutil
            term_h = shutil.get_terminal_size().lines
        except Exception:
            term_h = 24
        sys.stdout.write("\x1b7")
        for i in range(self.CHAR_H):
            row = term_h - self.CHAR_H + i
            sys.stdout.write(f"\x1b[{row};1H\x1b[K")
        sys.stdout.write("\x1b8")
        sys.stdout.flush()

    def start(self, state: str = STATE_ACTIVE) -> None:
        self._state = state
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.3)
            self._thread = None


def render_orb_demo(*, duration: float = 6.0) -> None:
    orb = ParticleOrb(num_particles=6)
    orb.start(ParticleOrb.STATE_ACTIVE)
    print("particles active (pink/blue)...")
    time.sleep(duration * 0.6)
    orb.set_state(ParticleOrb.STATE_DONE)
    print("particles done (orange)...")
    time.sleep(duration * 0.4)
    orb.stop()
    print("stopped")


if __name__ == "__main__":
    import sys as _sys
    arg = _sys.argv[1] if len(_sys.argv) > 1 else "banner"

    if arg == "banner":
        render_banner()
    elif arg == "small":
        print(render_small())
    elif arg == "glow":
        render_glow_demo(duration=8.0)
    elif arg == "orb":
        render_orb_demo(duration=6.0)
    elif arg == "all":
        render_banner()
        print("glow demo (8s)...")
        render_glow_demo(duration=8.0)
        print("orb demo (6s)...")
        render_orb_demo(duration=6.0)
        print("done")
