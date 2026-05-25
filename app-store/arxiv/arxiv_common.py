from __future__ import annotations

import json
import os
from pathlib import Path

MAX_RESULTS = 50
DEFAULT_STORAGE_PATH = Path.home() / ".arxiv-mcp-server" / "papers"
DEFAULT_BG_STATE_PATH = Path("/root/.arxiv-truffle/arxiv_bg_state.json")
DEFAULT_SETTINGS_PATH = Path("/root/.arxiv-truffle/arxiv_settings.json")


def get_storage_path() -> Path:
    raw = str(os.getenv("ARXIV_STORAGE_PATH", "")).strip()
    path = Path(raw) if raw else DEFAULT_STORAGE_PATH
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path

def get_settings_path() -> Path:
    raw = str(os.getenv("ARXIV_SETTINGS_PATH", "")).strip()
    path = Path(raw) if raw else DEFAULT_SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def load_settings() -> dict:
    path = get_settings_path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data
    except Exception:
        pass
    return {}

def save_settings(data: dict) -> None:
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

def is_background_enabled() -> bool:
    settings = load_settings()
    return settings.get("background_enabled", True)

def set_background_enabled(enabled: bool) -> None:
    settings = load_settings()
    settings["background_enabled"] = enabled
    save_settings(settings)

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
