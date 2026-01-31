from __future__ import annotations

THINK_TAGS = ["<think>", "</think>"]


def clean_response(response: str) -> str:
    return response.strip().replace("�", "")
