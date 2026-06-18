from __future__ import annotations

import os
from typing import Any

import httpx

EXA_SEARCH_URL = os.getenv("EXA_SEARCH_URL", "https://api.exa.ai/search")


async def verify_exa_api_key(api_key: str) -> tuple[bool, str]:
    key = (api_key or "").strip()
    if not key:
        return False, "Missing EXA_API_KEY"

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.post(
                EXA_SEARCH_URL,
                headers={
                    "x-api-key": key,
                    "content-type": "application/json",
                    "accept": "application/json",
                },
                json={
                    "query": "hello",
                    "numResults": 1,
                    "text": False,
                },
            )
    except httpx.TimeoutException:
        return False, "Exa verification timed out while calling the Search API"
    except httpx.HTTPError as exc:
        return False, f"Exa verification request failed: {exc}"

    if response.status_code in {401, 403}:
        return False, "Exa API key is invalid, expired, revoked, or lacks API access"
    if response.status_code == 429:
        return False, "Exa API rate limit reached during verification; retry shortly"
    if response.status_code >= 500:
        return False, f"Exa verification failed with upstream HTTP {response.status_code}"
    if response.status_code >= 400:
        return False, f"Exa verification failed with HTTP {response.status_code}"

    try:
        payload: dict[str, Any] = response.json()
    except ValueError:
        return False, "Exa verification failed: Search API response was not valid JSON"

    results = payload.get("results")
    if not isinstance(results, list):
        return False, "Exa verification failed: Search API response missing results list"

    return True, f"Exa API key verified. search_results_returned={len(results)}"
