#!/usr/bin/env python3
"""Local Kalshi credential verifier.

Runs two checks:
1) Direct API call via KalshiClient.get_balance()
2) Worker verify path via KalshiBackgroundWorker.verify()

This helps isolate:
- key/base-path/auth issues
- app-side verify wiring issues
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import httpx

from bg_worker import KalshiBackgroundWorker
from client import KalshiClient
from config import (
    KALSHI_API_KEY,
    KALSHI_BASE_URL,
    KALSHI_PRIVATE_KEY,
    normalize_private_key,
)


def _set_env_from_args(args: argparse.Namespace) -> None:
    if args.api_key:
        os.environ["KALSHI_API_KEY"] = args.api_key
    if args.private_key:
        os.environ["KALSHI_PRIVATE_KEY"] = args.private_key
    if args.private_key_file:
        with open(args.private_key_file, "r", encoding="utf-8") as f:
            os.environ["KALSHI_PRIVATE_KEY"] = f.read()
    if args.base_path:
        os.environ["KALSHI_BASE_PATH"] = args.base_path


def _load_effective_config() -> tuple[str, str, str]:
    api_key = os.getenv("KALSHI_API_KEY", KALSHI_API_KEY).strip()
    private_key = os.getenv("KALSHI_PRIVATE_KEY", KALSHI_PRIVATE_KEY)
    base_path = os.getenv("KALSHI_BASE_PATH", KALSHI_BASE_URL).strip()
    return api_key, private_key, base_path


async def _check_direct(api_key: str, private_key: str, base_path: str) -> bool:
    print("[1/2] Direct client auth check...")
    client = KalshiClient(
        api_key=api_key,
        private_key_pem=normalize_private_key(private_key),
        base_url=base_path,
    )
    try:
        data = await client.get_balance()
        balance = int(data.get("balance", 0))
        print(f"  PASS direct client auth. Balance: {balance}c")
        return True
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        body = ""
        try:
            body = error.response.text[:1000]
        except Exception:
            pass
        print(f"  FAIL direct client auth. HTTP {status}")
        if body:
            print(f"  Response: {body}")
        return False
    except Exception as error:
        print(f"  FAIL direct client auth. {type(error).__name__}: {error}")
        return False
    finally:
        await client.close()


async def _check_worker() -> bool:
    print("[2/2] Worker verify check...")
    worker = KalshiBackgroundWorker()
    try:
        ok, message = await worker.verify()
        if ok:
            print(f"  PASS worker verify. {message}")
        else:
            print(f"  FAIL worker verify. {message}")
        return ok
    finally:
        await worker.close()


async def _run() -> int:
    parser = argparse.ArgumentParser(description="Verify Kalshi credentials locally.")
    parser.add_argument("--api-key", help="Kalshi API key (overrides env)")
    parser.add_argument("--private-key", help="Kalshi private key PEM text (overrides env)")
    parser.add_argument("--private-key-file", help="Path to PEM private key file (overrides env)")
    parser.add_argument("--base-path", help="Kalshi base API path (overrides env)")
    args = parser.parse_args()

    _set_env_from_args(args)
    api_key, private_key, base_path = _load_effective_config()

    print("Effective config:")
    print(f"  KALSHI_BASE_PATH={base_path}")
    print(f"  KALSHI_API_KEY set={bool(api_key)}")
    print(f"  KALSHI_PRIVATE_KEY set={bool((private_key or '').strip())}")

    if not api_key or not private_key.strip():
        print("Missing KALSHI_API_KEY or KALSHI_PRIVATE_KEY.")
        return 2

    direct_ok = await _check_direct(api_key, private_key, base_path)

    try:
        worker_ok = await _check_worker()
    except Exception as error:
        print(f"  FAIL worker verify raised {type(error).__name__}: {error}")
        worker_ok = False

    if direct_ok and worker_ok:
        print("Result: credentials valid and verify path is working.")
        return 0
    if direct_ok and not worker_ok:
        print("Result: credentials likely valid, but verify path has an app-side issue.")
        return 3
    print("Result: credentials/base-path/auth are failing before app verify path.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))

