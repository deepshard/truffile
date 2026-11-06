from __future__ import annotations

from pathlib import Path
from typing import Any

from truffile.path_safety import resolve_path_within
from truffile.transport.client import TruffleClient


async def _upload_file(
    client: TruffleClient,
    src: Path,
    dest: str,
    spinner_cls: Any,
    arrow: str,
    color_dim: str,
    color_reset: str,
) -> None:
    spinner = spinner_cls(f"Uploading {src.name} {arrow} {dest}")
    spinner.start()
    result = await client.upload(src, dest)
    spinner.stop(success=True)
    print(f"  {color_dim}{result.bytes} bytes, sha256={result.sha256[:12]}...{color_reset}")


async def handle_files(
    step: dict[str, Any],
    *,
    client: TruffleClient,
    app_dir: Path,
    spinner_cls: Any,
    arrow: str,
    color_dim: str,
    color_reset: str,
    **_kw: Any,
) -> None:
    for f in step.get("files", []):
        src = resolve_path_within(app_dir, f["source"], label="Source file")
        dest = f["destination"]

        if src.is_dir():
            for child in sorted(src.rglob("*")):
                if child.is_file() and "__pycache__" not in str(child):
                    safe_child = resolve_path_within(
                        app_dir,
                        str(child.relative_to(app_dir)),
                        label="Source file",
                    )
                    rel = child.relative_to(src)
                    child_dest = f"{dest.rstrip('/')}/{rel}"
                    await _upload_file(client, safe_child, child_dest, spinner_cls, arrow, color_dim, color_reset)
        elif src.is_file():
            await _upload_file(client, src, dest, spinner_cls, arrow, color_dim, color_reset)
        else:
            raise FileNotFoundError(f"no such file: {src}")
