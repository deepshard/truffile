from __future__ import annotations


def build_env_prefix(env: dict[str, str] | None) -> str:
    """Build shell exports for env collected during earlier install steps."""
    if not env:
        return ""
    parts = []
    for key, val in env.items():
        escaped = val.replace("'", "'\\''")
        parts.append(f"export {key}='{escaped}'")
    return "; ".join(parts) + "; "
