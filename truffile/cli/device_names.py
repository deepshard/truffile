"""Canonical names shared by explicit pairing and interactive onboarding."""

import re


def normalize_device_name(raw: str) -> str:
    name = raw.strip().lower().rstrip(".").removesuffix(".local")
    if re.fullmatch(r"\d+(?:[-.]\d+)*", name):
        return "truffle-" + re.sub(r"\D", "", name)
    return name
