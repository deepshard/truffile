#!/usr/bin/env python3
# list all files in an app directory with their sizes
# usage: python scripts/list_app_files.py path/to/app/

import argparse
import sys
from pathlib import Path


def list_files(app_dir: Path) -> list[dict]:
    files = []
    for f in sorted(app_dir.rglob("*")):
        if f.is_dir() or "__pycache__" in str(f):
            continue
        rel = f.relative_to(app_dir)
        size = f.stat().st_size
        files.append({"path": str(rel), "size": size, "ext": f.suffix})
    return files


def main():
    parser = argparse.ArgumentParser(description="list app files")
    parser.add_argument("path", nargs="?", default=".", help="path to app directory")
    args = parser.parse_args()

    app_dir = Path(args.path).resolve()
    files = list_files(app_dir)

    py_files = [f for f in files if f["ext"] == ".py"]
    yaml_files = [f for f in files if f["ext"] in (".yaml", ".yml")]
    other = [f for f in files if f not in py_files and f not in yaml_files]

    if yaml_files:
        print("config:")
        for f in yaml_files:
            print(f"  {f['path']} ({f['size']} bytes)")

    if py_files:
        print("python:")
        for f in py_files:
            print(f"  {f['path']} ({f['size']} bytes)")

    if other:
        print("other:")
        for f in other:
            print(f"  {f['path']} ({f['size']} bytes)")

    total_size = sum(f["size"] for f in files)
    print(f"\ntotal: {len(files)} files, {total_size:,} bytes")


if __name__ == "__main__":
    main()
