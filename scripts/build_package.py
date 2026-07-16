#!/usr/bin/env python3
"""Stage Truffile's release-only Python packages from the pyfw source tree."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PACKAGE_FILES = (
    Path("truffile/app_runtime/__init__.py"),
    Path("truffle/app/app_runtime_pb2.py"),
)


def missing_package_inputs(repo_root: Path = REPO_ROOT) -> list[Path]:
    return [path for path in REQUIRED_PACKAGE_FILES if not (repo_root / path).is_file()]


def require_package_inputs(repo_root: Path = REPO_ROOT) -> None:
    missing = missing_package_inputs(repo_root)
    if not missing:
        return
    paths = ", ".join(str(path) for path in missing)
    raise RuntimeError(
        f"release package inputs are missing: {paths}. "
        "Run `python3.12 scripts/build_package.py --pyfw-path /path/to/pyfw` first."
    )


def resolve_pyfw_path(raw_path: str | None) -> Path:
    value = raw_path or os.environ.get("PYFW_PATH", "")
    if not value:
        raise RuntimeError("provide --pyfw-path or export PYFW_PATH")
    pyfw_path = Path(value).expanduser().resolve()
    runtime_init = pyfw_path / "python" / "app_runtime" / "__init__.py"
    if not runtime_init.is_file():
        raise RuntimeError(f"pyfw checkout is missing: {runtime_init}")
    return pyfw_path


def build_protos(pyfw_path: Path) -> None:
    build_script = pyfw_path / "python" / "tools" / "build_protos.py"
    if not build_script.is_file():
        raise RuntimeError(f"pyfw proto build script is missing: {build_script}")
    subprocess.run([sys.executable, str(build_script)], cwd=pyfw_path, check=True)


def _replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def stage_package_inputs(pyfw_path: Path, repo_root: Path = REPO_ROOT) -> None:
    app_runtime = pyfw_path / "python" / "app_runtime"
    truffle_protos = pyfw_path / "python" / "truffle"
    required_sources = (
        app_runtime / "__init__.py",
        truffle_protos / "app" / "app_runtime_pb2.py",
    )
    missing = [path for path in required_sources if not path.is_file()]
    if missing:
        raise RuntimeError(f"pyfw checkout is missing: {', '.join(str(path) for path in missing)}")

    _replace_tree(app_runtime, repo_root / "truffile" / "app_runtime")
    _replace_tree(truffle_protos, repo_root / "truffle")
    require_package_inputs(repo_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage app_runtime and generated Truffle protos from their pyfw source-of-truth"
    )
    parser.add_argument("--pyfw-path", default=None, help="path to a pyfw checkout")
    parser.add_argument(
        "--skip-proto-build",
        action="store_true",
        dest="skip_proto_build",
        help="use the protos already generated in pyfw",
    )
    args = parser.parse_args(argv)

    try:
        pyfw_path = resolve_pyfw_path(args.pyfw_path)
        if not args.skip_proto_build:
            build_protos(pyfw_path)
        stage_package_inputs(pyfw_path)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"error: {exc}\n")

    print(f"Staged release packages from {pyfw_path}")
    print("Next: python3.12 -m build && python3.12 scripts/verify_wheel.py dist/*.whl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
