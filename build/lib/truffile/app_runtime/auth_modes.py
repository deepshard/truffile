from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class PublicAuth:
    mode: str = "public"


@dataclass(frozen=True, slots=True)
class TextConfigAuth:
    fields: tuple[str, ...]
    mode: str = "text"

    def __init__(self, fields: list[str] | tuple[str, ...]) -> None:
        object.__setattr__(self, "fields", tuple(fields))
        object.__setattr__(self, "mode", "text")


@dataclass(frozen=True, slots=True)
class OAuthAuth:
    provider: str
    token_file: str
    mode: str = "oauth"


@dataclass(frozen=True, slots=True)
class VncAuth:
    session_dir: str
    mode: str = "vnc"


def load_required_env(name: str) -> str:
    value = str(os.getenv(name, "")).strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
