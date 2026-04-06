#!/usr/bin/env python3
# check python files in an app directory for syntax errors and basic import issues
# usage: python scripts/check_python.py path/to/app/

import argparse
import ast
import sys
from pathlib import Path


def check_syntax(filepath: Path) -> tuple[bool, str]:
    try:
        source = filepath.read_text(encoding="utf-8")
        ast.parse(source, filename=str(filepath))
        return True, "ok"
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def check_app_dir(app_dir: Path) -> tuple[int, int, list[str]]:
    passed = 0
    failed = 0
    errors: list[str] = []

    for py_file in sorted(app_dir.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        ok, msg = check_syntax(py_file)
        rel = py_file.relative_to(app_dir)
        if ok:
            passed += 1
        else:
            failed += 1
            errors.append(f"  {rel}: {msg}")

    return passed, failed, errors


def main():
    parser = argparse.ArgumentParser(description="check python syntax in app directory")
    parser.add_argument("path", nargs="?", default=".", help="path to app directory")
    args = parser.parse_args()

    app_dir = Path(args.path).resolve()
    passed, failed, errors = check_app_dir(app_dir)

    for e in errors:
        print(e)

    total = passed + failed
    if failed == 0:
        print(f"\n  all {total} python files ok")
    else:
        print(f"\n  {failed}/{total} files have errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
