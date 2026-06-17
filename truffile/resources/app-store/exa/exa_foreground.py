"""Compatibility shim for the old Exa foreground module name."""

from foreground import ExaForegroundApp, app, main, verify


__all__ = ["ExaForegroundApp", "app", "main", "verify"]


if __name__ == "__main__":
    raise SystemExit(main())
