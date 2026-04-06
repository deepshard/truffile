#!/usr/bin/env python3
# fetch example apps from the truffile repo for reference
# usage: python scripts/fetch_repo.py [--app kalshi]

import argparse
import json
import sys

try:
    import httpx
except ImportError:
    print("install httpx: pip install httpx")
    sys.exit(1)

REPO = "deepshard/truffile"
API_BASE = f"https://api.github.com/repos/{REPO}"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main"


def list_example_apps() -> list[str]:
    url = f"{API_BASE}/contents/app-store"
    try:
        resp = httpx.get(url, timeout=15.0)
        if resp.status_code != 200:
            return []
        entries = resp.json()
        return [e["name"] for e in entries if e["type"] == "dir"]
    except Exception:
        return []


def fetch_app_file(app_name: str, filename: str) -> str:
    url = f"{RAW_BASE}/app-store/{app_name}/{filename}"
    try:
        resp = httpx.get(url, timeout=15.0)
        return resp.text if resp.status_code == 200 else f"not found: {url}"
    except Exception as e:
        return f"error: {e}"


def fetch_app_truffile(app_name: str) -> str:
    return fetch_app_file(app_name, "truffile.yaml")


def list_app_files(app_name: str) -> list[str]:
    url = f"{API_BASE}/contents/app-store/{app_name}"
    try:
        resp = httpx.get(url, timeout=15.0)
        if resp.status_code != 200:
            return []
        return [e["name"] for e in resp.json()]
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(description="fetch example apps from truffile repo")
    parser.add_argument("--app", type=str, default=None, help="app name to inspect")
    parser.add_argument("--file", type=str, default=None, help="specific file to fetch")
    parser.add_argument("--list", action="store_true", help="list example apps")
    args = parser.parse_args()

    if args.list:
        apps = list_example_apps()
        for a in apps:
            print(f"  {a}")
        return

    if args.app and args.file:
        print(fetch_app_file(args.app, args.file))
    elif args.app:
        print(f"files in {args.app}:")
        for f in list_app_files(args.app):
            print(f"  {f}")
        print(f"\ntruffile.yaml:")
        print(fetch_app_truffile(args.app))
    else:
        apps = list_example_apps()
        print(f"example apps ({len(apps)}):")
        for a in apps:
            print(f"  {a}")


if __name__ == "__main__":
    main()
