"""Clean CLI error handling — catches Ctrl-C and unhandled exceptions."""
from __future__ import annotations

import os
import sys

_RED = "\033[91m"
_RST = "\033[0m"
_CLR = "\033[K"


class CLIGuard:
    """Context manager that turns ugly tracebacks into clean one-liners.

    Usage::

        guard = CLIGuard()
        with guard:
            run_stuff()
        sys.exit(guard.code)

    Set ``TRUFFILE_DEBUG=1`` to see full tracebacks for non-interrupt errors.
    """

    def __init__(self) -> None:
        self.code: int = 0
        self._debug = os.environ.get("TRUFFILE_DEBUG", "") not in ("", "0", "false")

    def __enter__(self) -> CLIGuard:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        if exc_type is None:
            return False

        if issubclass(exc_type, KeyboardInterrupt):
            sys.stderr.write(f"\r{_CLR}{_RED}✗{_RST} Cancelled\n")
            sys.stderr.flush()
            self.code = 130
            return True

        if issubclass(exc_type, EOFError):
            sys.stderr.write("\n")
            sys.stderr.flush()
            self.code = 0
            return True

        if issubclass(exc_type, Exception):
            if self._debug:
                return False
            sys.stderr.write(f"{_RED}✗ Error:{_RST} {exc_val}\n")
            sys.stderr.flush()
            self.code = 1
            return True

        return False
