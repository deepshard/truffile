#!/usr/bin/env python3
# fetch truffle docs from docs.truffle.net for context
# usage: python scripts/fetch_docs.py [--section getting-started]

import argparse
import json
import sys

try:
    import httpx
except ImportError:
    print("install httpx: pip install httpx")
    sys.exit(1)

DOCS_BASE = "https://docs.truffle.net"

SECTIONS = [
    "getting-started",
    "apps/overview",
    "apps/foreground",
    "apps/background",
    "apps/manifest",
    "apps/testing",
    "apps/auth",
    "sdk/overview",
]


def fetch_section(section: str) -> str:
    url = f"{DOCS_BASE}/{section}"
    try:
        resp = httpx.get(url, timeout=15.0, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
        return f"error: {resp.status_code}"
    except Exception as e:
        return f"error: {e}"


def main():
    parser = argparse.ArgumentParser(description="fetch truffle docs")
    parser.add_argument("--section", type=str, default=None, help="specific section to fetch")
    parser.add_argument("--list", action="store_true", help="list available sections")
    args = parser.parse_args()

    if args.list:
        for s in SECTIONS:
            print(f"  {s}")
        return

    if args.section:
        content = fetch_section(args.section)
        print(content)
    else:
        for s in SECTIONS:
            print(f"\n--- {s} ---")
            content = fetch_section(s)
            print(content[:500])


if __name__ == "__main__":
    main()
