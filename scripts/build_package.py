#!/usr/bin/env python3
# if youre reading this plz go make apps lol
# copies app_runtime from pyfw and rebuilds protos for truffile packaging.
#
# usage:
#   python scripts/build_package.py --pyfw-path /path/to/pyfw
#
# or set PYFW_PATH in .env:
#   echo "PYFW_PATH=/Users/me/work/pyfw" > .env
#   python scripts/build_package.py
#
# what it does:
#   1. copies python/app_runtime/ from pyfw into truffile/app_runtime/
#   2. rebuilds protos in pyfw (if needed) and copies truffle/ proto package
#   3. strips internal-only modules (browser/web_fingerprint) from the public build

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TRUFFILE_PKG = REPO_ROOT / "truffile"
TRUFFLE_PROTO_PKG = REPO_ROOT / "truffle"

def load_env():
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def resolve_pyfw_path(cli_arg: str | None) -> Path:
    raw = cli_arg or os.environ.get("PYFW_PATH", "")
    if not raw:
        print("error: --pyfw-path not provided and PYFW_PATH not set")
        print("set it via cli arg or in .env file")
        sys.exit(1)
    path = Path(raw).resolve()
    if not (path / "python" / "app_runtime").exists():
        print(f"error: {path}/python/app_runtime does not exist")
        sys.exit(1)
    return path


def build_protos(pyfw_path: Path):
    build_script = pyfw_path / "python" / "tools" / "build_protos.py"
    if not build_script.exists():
        print("warning: proto build script not found, skipping proto rebuild")
        return
    print("building protos in pyfw...")
    subprocess.run(
        [sys.executable, str(build_script)],
        cwd=str(pyfw_path),
        check=True,
    )
    print("protos built")


def copy_app_runtime(pyfw_path: Path):
    src = pyfw_path / "python" / "app_runtime"
    dst = TRUFFILE_PKG / "app_runtime"

    if dst.exists():
        shutil.rmtree(dst)

    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"copied app_runtime ({sum(1 for _ in dst.rglob('*.py'))} py files)")


def copy_protos(pyfw_path: Path):
    src = pyfw_path / "python" / "truffle"
    dst = TRUFFLE_PROTO_PKG

    if not src.exists():
        print("warning: pyfw truffle/ proto package not found, keeping existing vendored protos")
        return

    if dst.exists():
        shutil.rmtree(dst)

    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(f"copied truffle protos ({sum(1 for _ in dst.rglob('*.py'))} py files)")


def main():
    load_env()

    parser = argparse.ArgumentParser(description="build truffile package with app_runtime from pyfw")
    parser.add_argument("--pyfw-path", type=str, default=None)
    parser.add_argument("--skip-protos", action="store_true", help="skip proto rebuild")
    args = parser.parse_args()

    pyfw_path = resolve_pyfw_path(args.pyfw_path)
    print(f"using pyfw at: {pyfw_path}")

    if not args.skip_protos:
        build_protos(pyfw_path)

    copy_app_runtime(pyfw_path)
    copy_protos(pyfw_path)

    print("\npackage ready. run: pip install -e . to test locally")


if __name__ == "__main__":
    main()
