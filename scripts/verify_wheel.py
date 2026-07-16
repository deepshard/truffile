#!/usr/bin/env python3
"""Verify the packages and imports required by a released Truffile wheel."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


REQUIRED_WHEEL_FILES = (
    "truffile/sdk.py",
    "truffile/app_runtime/__init__.py",
    "truffile/app_runtime/foreground.py",
    "truffile/app_runtime/background/runtime.py",
    "truffle/app/app_pb2.py",
    "truffle/app/app_runtime_pb2.py",
    "truffle/app/background_pb2.py",
    "truffle/os/app_queries_pb2.py",
    "truffle/os/builder_pb2.py",
    "truffle/os/client_session_pb2.py",
    "truffle/os/truffleos_pb2_grpc.py",
)


def missing_wheel_files(wheel_path: Path) -> list[str]:
    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())
    return [path for path in REQUIRED_WHEEL_FILES if path not in names]


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def verify_installed_wheel(wheel_path: Path) -> None:
    wheel_path = wheel_path.resolve()
    with tempfile.TemporaryDirectory(prefix="truffile-wheel-") as temp_dir:
        temp = Path(temp_dir)
        venv_dir = temp / ".venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        python = _venv_python(venv_dir)
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                str(wheel_path),
            ],
            check=True,
        )
        smoke_test = """
import importlib.util
import tempfile
from pathlib import Path
from types import SimpleNamespace

from truffile.app_runtime import BackgroundWorkerApp, ForegroundApp
from truffile.client import TruffleClient
from truffile.cli.create import cmd_create
from truffile.schedule import parse_runtime_policy
from truffile.sdk import AppHarness

with tempfile.TemporaryDirectory() as root:
    result = cmd_create(SimpleNamespace(name="wheel-smoke", path=root))
    if result != 0:
        raise SystemExit(result)
    entrypoint = Path(root) / "wheel-smoke" / "wheel_smoke_foreground.py"
    spec = importlib.util.spec_from_file_location("wheel_smoke_foreground", entrypoint)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    background = Path(root) / "wheel-smoke" / "wheel_smoke_background.py"
    spec = importlib.util.spec_from_file_location("wheel_smoke_background", background)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
"""
        subprocess.run([str(python), "-c", smoke_test], check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="verify a built Truffile wheel in a fresh environment")
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args(argv)
    wheel_path = args.wheel.expanduser().resolve()
    if not wheel_path.is_file():
        parser.error(f"wheel does not exist: {wheel_path}")

    missing = missing_wheel_files(wheel_path)
    if missing:
        parser.exit(1, f"error: wheel is missing: {', '.join(missing)}\n")
    verify_installed_wheel(wheel_path)
    print(f"Verified {wheel_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
