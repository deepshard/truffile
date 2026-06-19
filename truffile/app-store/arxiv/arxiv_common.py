from __future__ import annotations

import os
from pathlib import Path

MAX_RESULTS = 50
DEFAULT_STORAGE_PATH = Path.home() / ".arxiv-mcp-server" / "papers"
DEFAULT_BG_STATE_PATH = Path("/root/.arxiv-truffle/arxiv_bg_state.json")


def get_storage_path() -> Path:
    raw = str(os.getenv("ARXIV_STORAGE_PATH", "")).strip()
    path = Path(raw) if raw else DEFAULT_STORAGE_PATH
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_bg_state_path() -> Path:
    raw = str(os.getenv("ARXIV_BG_STATE_PATH", "")).strip()
    path = Path(raw) if raw else DEFAULT_BG_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def parse_research_interests(raw: str | None) -> list[str]:
    if not raw:
        return []
    normalized = raw.replace("\n", ",")
    out: list[str] = []
    seen: set[str] = set()
    for part in normalized.split(","):
        interest = part.strip()
        if not interest:
            continue
        key = interest.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(interest)
    return out

