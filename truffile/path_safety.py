from __future__ import annotations

from pathlib import Path


def resolve_path_within(root: Path, raw_path: str, *, label: str = "Path") -> Path:
    resolved_root = root.resolve()
    resolved = (resolved_root / raw_path).resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"{label} must stay within {resolved_root}")
    return resolved
