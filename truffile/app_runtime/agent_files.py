from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote, unquote, urlparse

import aiohttp

from .errors import AppRuntimeFailure


DEFAULT_AGENT_FILE_MAX_BYTES = 50 * 1024 * 1024
AGENT_FILE_CHUNK_BYTES = 1024 * 1024
AGENT_FILE_USER_AGENT = "truffle-app-runtime-agent-file/1.0"
DEFAULT_GATEWAY_ORIGIN = "http://10.22.0.1"
DEFAULT_ALLOWED_GATEWAY_HOSTS = {
    "10.22.0.1",
    "10.22.0.1:80",
}


@dataclass(frozen=True, slots=True)
class MaterializedAgentFile:
    """A bounded copy of an agent-produced file inside the app sandbox."""

    local_path: Path
    name: str
    size: int
    mime_type: str
    sha256: str
    source_url: str
    source_path: str = ""


@dataclass(frozen=True, slots=True)
class _MaterializePlan:
    parsed: dict[str, Any]
    source_url: str
    target: Path
    tmp_path: Path
    max_bytes: int


@dataclass(frozen=True, slots=True)
class _DownloadedAgentFile:
    size: int
    mime_type: str
    sha256: str


async def materialize_agent_file(
    file_ref: str | Mapping[str, Any],
    *,
    max_bytes: int = DEFAULT_AGENT_FILE_MAX_BYTES,
    destination_dir: Path | str | None = None,
    timeout_seconds: float = 30.0,
) -> MaterializedAgentFile:
    """Materialize an agent file reference into this app container asynchronously.

    The app never gets host mounts or direct access to the agent container. It
    receives a size-limited copy through the Truffle file gateway.
    """

    plan = _prepare_materialization(file_ref, max_bytes=max_bytes, destination_dir=destination_dir)
    try:
        downloaded = await _download_gateway_file(plan, timeout_seconds=timeout_seconds)
        return await asyncio.to_thread(_finalize_materialized_file, plan, downloaded)
    except Exception:
        await asyncio.to_thread(_unlink_quietly, plan.tmp_path)
        raise


def _prepare_materialization(
    file_ref: str | Mapping[str, Any],
    *,
    max_bytes: int,
    destination_dir: Path | str | None,
) -> _MaterializePlan:
    parsed = _parse_file_ref(file_ref)
    source_url = _source_url_for_ref(parsed)
    expected_size = _optional_int(parsed.get("size"))
    if expected_size is not None and expected_size > max_bytes:
        raise AppRuntimeFailure(f"agent file reference exceeds {max_bytes} bytes")

    target_dir = Path(destination_dir) if destination_dir is not None else _default_destination_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    name = _safe_filename(str(parsed.get("name") or "")) or _filename_from_ref(parsed) or "agent-file"
    target = _unique_destination(target_dir, name)
    tmp_path = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
    return _MaterializePlan(
        parsed=parsed,
        source_url=source_url,
        target=target,
        tmp_path=tmp_path,
        max_bytes=max_bytes,
    )


def _finalize_materialized_file(plan: _MaterializePlan, downloaded: _DownloadedAgentFile) -> MaterializedAgentFile:
    expected_sha = str(plan.parsed.get("sha256") or "").strip().lower()
    if expected_sha and expected_sha != downloaded.sha256:
        raise AppRuntimeFailure("agent file sha256 mismatch")

    mime_type = downloaded.mime_type or mimetypes.guess_type(plan.target.name)[0] or "application/octet-stream"
    plan.tmp_path.replace(plan.target)

    return MaterializedAgentFile(
        local_path=plan.target,
        name=plan.target.name,
        size=downloaded.size,
        mime_type=mime_type,
        sha256=downloaded.sha256,
        source_url=plan.source_url,
        source_path=str(plan.parsed.get("path") or plan.parsed.get("absolute_path") or ""),
    )


async def _download_gateway_file(plan: _MaterializePlan, *, timeout_seconds: float) -> _DownloadedAgentFile:
    digest = hashlib.sha256()
    size = 0
    mime_type = str(plan.parsed.get("mime_type") or plan.parsed.get("mime") or "").strip()
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            plan.source_url,
            headers={"User-Agent": AGENT_FILE_USER_AGENT},
            allow_redirects=False,
        ) as response:
            error_text = ""
            if response.status >= 400:
                error_text = (await response.content.read(300)).decode("utf-8", errors="replace")
            _validate_response_status(response.status, error_text)
            _validate_content_length(response.headers.get("Content-Length"), max_bytes=plan.max_bytes)
            content_type = _media_type(response.headers.get("Content-Type", ""))
            if content_type:
                mime_type = content_type
            with plan.tmp_path.open("wb") as out:
                async for chunk in response.content.iter_chunked(AGENT_FILE_CHUNK_BYTES):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > plan.max_bytes:
                        raise AppRuntimeFailure(f"agent file download exceeds {plan.max_bytes} bytes")
                    digest.update(chunk)
                    await asyncio.to_thread(out.write, chunk)
    return _DownloadedAgentFile(size=size, mime_type=mime_type, sha256=digest.hexdigest())


def _validate_response_status(status: int, body_text: str) -> None:
    if 300 <= status < 400:
        raise AppRuntimeFailure("agent file gateway redirects are not allowed")
    if status >= 400:
        raise AppRuntimeFailure(f"agent file gateway request failed ({status}): {body_text[:300]}")


def _validate_content_length(content_length: str | None, *, max_bytes: int) -> None:
    if not content_length:
        return
    try:
        length = int(content_length)
    except ValueError:
        return
    if length > max_bytes:
        raise AppRuntimeFailure(f"agent file download exceeds {max_bytes} bytes")


def _media_type(content_type: str) -> str:
    return str(content_type or "").split(";", 1)[0].strip()


def _parse_file_ref(file_ref: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(file_ref, Mapping):
        out = dict(file_ref)
        if not any(str(out.get(key) or "").strip() for key in ("path", "absolute_path", "local_path", "url")):
            raise AppRuntimeFailure("file_ref must include path, absolute_path, local_path, or url")
        return out
    raw = str(file_ref or "").strip()
    if not raw:
        raise AppRuntimeFailure("file_ref is required")
    if raw.startswith("http://") or raw.startswith("https://") or raw.startswith("/agent/"):
        return {"url": raw}
    return {"path": raw}


def _source_url_for_ref(ref: Mapping[str, Any]) -> str:
    url = str(ref.get("url") or "").strip()
    if url:
        return _validate_gateway_url(url)

    path = str(ref.get("path") or ref.get("absolute_path") or ref.get("local_path") or "").strip()
    if not path:
        raise AppRuntimeFailure("agent file path is required")
    if not Path(path).is_absolute():
        raise AppRuntimeFailure("agent file path must be absolute")
    return _agent_file_url_for_path(path)


def _validate_gateway_url(url: str) -> str:
    if url.startswith("/agent/"):
        parsed_relative = urlparse(url)
        if parsed_relative.query or parsed_relative.fragment:
            raise AppRuntimeFailure("agent file URL must not include query parameters or fragments")
        route_path = parsed_relative.path
        origin = _gateway_origin()
    else:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise AppRuntimeFailure("agent file URL must use http or https")
        if parsed.netloc not in _allowed_gateway_hosts():
            raise AppRuntimeFailure("agent file URL host is not an allowed Truffle gateway host")
        if parsed.query or parsed.fragment:
            raise AppRuntimeFailure("agent file URL must not include query parameters or fragments")
        route_path = parsed.path
        origin = f"{parsed.scheme}://{parsed.netloc}"

    expected_prefix = _agent_file_route_prefix()
    if not route_path.startswith(expected_prefix):
        raise AppRuntimeFailure("agent file URL does not match this app user's file route")
    suffix = route_path.removeprefix(expected_prefix)
    suffix_parts = [unquote(part) for part in suffix.split("/")]
    if not suffix or any(part in {"", ".", ".."} or "/" in part or "\\" in part for part in suffix_parts):
        raise AppRuntimeFailure("agent file URL path is invalid")
    return f"{origin}{route_path}"


def _agent_file_url_for_path(path: str) -> str:
    prefix = _agent_file_route_prefix()
    encoded = "/".join(quote(part) for part in Path(path).parts if part != "/")
    if not encoded:
        raise AppRuntimeFailure("agent file path must not resolve to root")
    return f"{_gateway_origin()}{prefix}{encoded}"


def _agent_file_route_prefix() -> str:
    configured = str(os.getenv("TRUFFLE_AGENT_FILE_ROUTE_PREFIX", "") or "").strip()
    if configured:
        return configured if configured.endswith("/") else f"{configured}/"
    user_uuid = str(os.getenv("APP_USER_UUID", "") or "").strip()
    if not user_uuid:
        raise AppRuntimeFailure("APP_USER_UUID is required to resolve agent file paths")
    return f"/agent/{user_uuid}/files/"


def _gateway_origin() -> str:
    origin = str(os.getenv("TRUFFLE_FILE_GATEWAY_ORIGIN", "") or "").strip() or DEFAULT_GATEWAY_ORIGIN
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AppRuntimeFailure("TRUFFLE_FILE_GATEWAY_ORIGIN must be an http(s) origin")
    if parsed.netloc not in _allowed_gateway_hosts():
        raise AppRuntimeFailure("TRUFFLE_FILE_GATEWAY_ORIGIN host is not allowed")
    return f"{parsed.scheme}://{parsed.netloc}"


def _allowed_gateway_hosts() -> set[str]:
    configured = str(os.getenv("TRUFFLE_FILE_GATEWAY_ALLOWED_HOSTS", "") or "").strip()
    if not configured:
        return set(DEFAULT_ALLOWED_GATEWAY_HOSTS)
    return {item.strip() for item in configured.split(",") if item.strip()}


def _default_destination_dir() -> Path:
    configured = str(os.getenv("TRUFFLE_AGENT_FILE_MATERIALIZE_DIR", "") or "").strip()
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "truffle-agent-files"


def _filename_from_ref(ref: Mapping[str, Any]) -> str:
    for key in ("path", "absolute_path", "local_path", "url"):
        raw = str(ref.get(key) or "").strip()
        if not raw:
            continue
        parsed = urlparse(raw)
        candidate = Path(unquote(parsed.path if parsed.scheme else raw)).name
        safe = _safe_filename(candidate)
        if safe:
            return safe
    return ""


def _safe_filename(value: str) -> str:
    name = value.strip().replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:160]


def _unique_destination(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(filename) or "agent-file"
    target = directory / safe
    if not target.exists():
        return target
    stem = target.stem or "agent-file"
    suffix = target.suffix
    for index in range(1, 10_000):
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    return directory / f"{stem}-{uuid.uuid4().hex}{suffix}"


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass
