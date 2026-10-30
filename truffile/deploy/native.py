"""Bundle uploads and account setup through the firmware's native installer."""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import hashlib
import math
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import grpc
import httpx
import yaml
from truffle.os.installer_pb2 import AppInstallRequest, APP_INSTALL_SOURCE_TYPE_FILE

MAX_BUNDLE_BYTES = 200 * 1024 * 1024
_EXCLUDED = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _manifest(raw: str) -> dict:
    config = yaml.safe_load(raw)
    if not isinstance(config, dict) or not isinstance(config.get("metadata"), dict):
        raise ValueError("truffile.yaml must contain a metadata mapping")
    version = config.get("truffile_version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("truffile_version must be a positive integer")
    for key in ("name", "bundle_id"):
        if not isinstance(config["metadata"].get(key), str) or not config["metadata"][key].strip():
            raise ValueError(f"metadata.{key} is required")
    return config


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name


def bundle_files(directory: Path):
    ignore = directory / ".truffleignore"
    patterns = [line.strip() for line in ignore.read_text().splitlines()
                if line.strip() and not line.lstrip().startswith("#")] if ignore.exists() else []
    for path in sorted(directory.rglob("*")):
        rel = path.relative_to(directory).as_posix()
        parts = PurePosixPath(rel).parts
        if any(p in _EXCLUDED for p in parts):
            continue
        if path.name in {".env", ".DS_Store", ".truffleignore"} or path.name.startswith(".env.") or path.suffix == ".truffle":
            continue
        if any(fnmatch.fnmatchcase(rel, p) or rel.startswith(p.rstrip("/") + "/") for p in patterns):
            continue
        if path.is_symlink():
            raise ValueError(f"Bundle symlinks are not supported: {rel}")
        if path.is_file():
            yield path, rel


@dataclass
class NativeBundle:
    path: Path
    config: dict
    sha256: str


@contextlib.contextmanager
def prepare_bundle(source: Path, *, exclude_paths=()):
    """Package without rewriting the manifest. Firmware performs semantic validation."""
    source = source.resolve()
    excluded = {Path(path).resolve() for path in exclude_paths if path}
    with tempfile.TemporaryDirectory(prefix="truffile-bundle-") as temporary:
        archive = Path(temporary) / "app.truffle"
        if source.is_dir():
            config = _manifest((source / "truffile.yaml").read_text())
            total = 0
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
                for path, rel in bundle_files(source):
                    if path.resolve() in excluded:
                        continue
                    total += path.stat().st_size
                    if total > MAX_BUNDLE_BYTES:
                        raise ValueError("Bundle exceeds the 200 MiB limit")
                    info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
                    info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    output.writestr(info, path.read_bytes())
        elif source.is_file():
            if source.stat().st_size > MAX_BUNDLE_BYTES:
                raise ValueError("Bundle exceeds the 200 MiB limit")
            # Snapshot the supplied bundle so its hash and uploaded bytes agree.
            archive.write_bytes(source.read_bytes())
            config = None
        else:
            raise ValueError(f"App directory or .truffle bundle not found: {source}")
        with zipfile.ZipFile(archive) as contents:
            entries = contents.infolist()
            if sum(item.file_size for item in entries) > MAX_BUNDLE_BYTES:
                raise ValueError("Expanded bundle exceeds the 200 MiB limit")
            if any(not _safe_member(item.filename) or (item.external_attr >> 16) & 0o170000 == 0o120000 for item in entries):
                raise ValueError("Bundle contains an unsafe path or symlink")
            if len({item.filename for item in entries}) != len(entries):
                raise ValueError("Bundle contains duplicate file paths")
            config = _manifest(contents.read("truffile.yaml").decode("utf-8"))
        yield NativeBundle(archive, config, hashlib.sha256(archive.read_bytes()).hexdigest())


async def install_native(client, *, mode: str, handle_modal, progress=None,
                         bundle: NativeBundle | None = None, app_uuid: str | None = None,
                         connection_id: str | None = None, timeout: float = 900) -> dict:
    """Run one install operation; never automatically retry a mutation."""
    if not client.stub:
        raise RuntimeError("not connected")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive finite number")
    if mode not in {"install", "update", "replace", "add", "reconnect"}:
        raise ValueError("unknown install mode")
    if mode != "install" and not app_uuid:
        raise ValueError("app_uuid is required")
    if mode == "reconnect" and not connection_id:
        raise ValueError("connection_id is required")
    if mode in {"install", "update", "replace"} and bundle is None:
        raise ValueError("bundle is required")
    if mode in {"add", "reconnect"} and bundle is not None:
        raise ValueError("account setup uses the installed bundle; do not supply a bundle")
    metadata = list(client._metadata)
    if mode in {"update", "replace"}:
        if not await client.supports_developer_uploads():
            raise RuntimeError("This firmware does not expose developer uploads. Upgrade PyFW before using --update or --replace; no app was changed.")
        metadata.append(("truffile-developer-upload", "1"))
    initial = AppInstallRequest()
    if mode in {"install", "replace"}:
        source = initial.start_new.source
        if mode == "replace":
            initial.start_new.replace_app_uuid = app_uuid
    elif mode == "update":
        initial.start_update.app_uuid = app_uuid
        source = initial.start_update.source
    elif mode == "add":
        initial.start_add_connection.app_uuid = app_uuid
    else:
        initial.start_reconnect.app_uuid = app_uuid
        initial.start_reconnect.connection_id = connection_id
    if bundle is not None:
        source.source_type = APP_INSTALL_SOURCE_TYPE_FILE
        source.release.bundle_sha256 = bundle.sha256
        source.release.display_version = f"local-{bundle.sha256[:12]}"

    stream = client.stub.Apps_InstallApp(metadata=metadata)
    finished = False
    uploaded = False
    async def abort():
        request = AppInstallRequest()
        request.user_action.abort.SetInParent()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(stream.write(request), 2)
    try:
        async with asyncio.timeout(timeout):
            await stream.write(initial)
            while True:
                response = await stream.read()
                if response is grpc.aio.EOF:
                    raise RuntimeError("Installer disconnected before completion. Inspect the app before retrying.")
                if response.HasField("install_error"):
                    raise RuntimeError(response.install_error.error_message)
                if response.HasField("install_loading") and progress:
                    progress(response.install_loading.loading_message)
                if not response.HasField("install_modal"):
                    continue
                modal = response.install_modal
                if modal.HasField("upload_file_modal"):
                    route = modal.upload_file_modal.upload_uri_path
                    if bundle is None or uploaded or not re.fullmatch(r"/containers/[A-Za-z0-9_-]+/source/upload", route):
                        raise RuntimeError("Installer returned an unexpected upload request")
                    base = client.address if "://" in client.address else f"http://{client.address}"
                    async with httpx.AsyncClient(timeout=90, trust_env=False) as http:
                        with bundle.path.open("rb") as data:
                            result = await http.post(base.rstrip("/") + route,
                                files={"file": ("app.truffle", data, "application/zip")},
                                headers=dict(client._metadata))
                        result.raise_for_status()
                    uploaded = True
                elif modal.HasField("finish_modal"):
                    finish = modal.finish_modal
                    finished = True
                    if bundle is not None and not uploaded:
                        raise RuntimeError("Firmware completed without receiving the bundle. Inspect the app; the requested code was not uploaded.")
                    # A finish modal is terminal; some firmware closes the stream
                    # immediately. Never write another action after it.
                    return {"app_uuid": finish.app_uuid, "connection_id": finish.connection_id,
                            "mode": mode, "bundle_sha256": bundle.sha256 if bundle else None}
                else:
                    action = await handle_modal(modal)
                    if action is not None:
                        request = AppInstallRequest()
                        request.user_action.CopyFrom(action)
                        await stream.write(request)
    except TimeoutError as exc:
        raise RuntimeError("Installer timed out. Cancellation was requested; inspect the app before retrying.") from exc
    finally:
        if not finished:
            await abort()
        stream.cancel()
