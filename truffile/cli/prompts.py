"""Terminal prompts that do not hold the event loop or block cancellation."""

import asyncio
import getpass
import os
import sys
import threading


def interactive(args) -> bool:
    return sys.stdin.isatty() and not getattr(args, "json", False) and not getattr(args, "non_interactive", False)


async def prompt(message: str, *, secret: bool = False) -> str:
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    if os.name == "posix" and sys.stdin.isatty():
        import termios
        fd = sys.stdin.fileno()
        previous = termios.tcgetattr(fd)
        try:
            if secret:
                hidden = list(previous)
                hidden[3] &= ~termios.ECHO
                termios.tcsetattr(fd, termios.TCSANOW, hidden)
            print(message, end="", file=sys.stderr, flush=True)
            def ready():
                if future.done():
                    return
                value = sys.stdin.readline()
                if value:
                    future.set_result(value.rstrip("\r\n"))
                else:
                    future.set_exception(ValueError("Input cancelled"))
            loop.add_reader(fd, ready)
            return await future
        finally:
            loop.remove_reader(fd)
            termios.tcsetattr(fd, termios.TCSANOW, previous)
            if secret:
                print(file=sys.stderr)

    def finish(value=None, error=None):
        if not future.done():
            future.set_exception(error) if error else future.set_result(value)

    def read():
        try:
            if secret:
                value = getpass.getpass(message, stream=sys.stderr)
            else:
                print(message, end="", file=sys.stderr, flush=True)
                value = input()
            loop.call_soon_threadsafe(finish, value, None)
        except (EOFError, KeyboardInterrupt):
            try:
                loop.call_soon_threadsafe(finish, None, ValueError("Input cancelled"))
            except RuntimeError:
                pass
        except RuntimeError:
            pass  # The command was cancelled and its event loop has closed.

    threading.Thread(target=read, daemon=True).start()
    return await future


async def choose(items, *, question, label, args):
    if not items:
        raise ValueError("No matching apps or accounts found")
    if not interactive(args):
        choices = "; ".join(label(item) for item in items)
        raise ValueError(f"{question} Specify an exact name or ID. Choices: {choices}")
    print(question, file=sys.stderr)
    for index, item in enumerate(items, 1):
        print(f"  {index}. {label(item)}", file=sys.stderr)
    value = (await prompt("Choose a number (blank cancels): ")).strip()
    if not value.isdecimal() or not 1 <= int(value) <= len(items):
        raise ValueError("Selection cancelled or invalid")
    return items[int(value) - 1]


async def confirm(message, args):
    if getattr(args, "yes", False):
        return
    if not interactive(args):
        raise ValueError(message + " Pass --yes to confirm in a script.")
    if (await prompt(message + " Continue? [y/N] ")).strip().casefold() not in {"y", "yes"}:
        raise ValueError("Cancelled; no change was requested")
