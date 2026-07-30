from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlparse

from truffile.path_safety import resolve_path_within


logger = logging.getLogger("truffile.obsidian_bridge")


@dataclass(frozen=True)
class ObsidianBridgeConfig:
    vault_path: Path
    token: str
    bind_host: str
    advertise_host: str
    port: int


def describe_vault_permission_error(path: Path) -> str:
    if sys.platform == "darwin":
        return (
            f"macOS blocked access to the vault path: {path}. "
            "Grant your terminal app access to that folder in System Settings > "
            "Privacy & Security > Files and Folders, or grant Full Disk Access, "
            "then rerun `truffile obsidian serve`."
        )
    return f"Permission denied for vault path: {path}"


def ensure_vault_access(path: Path) -> None:
    try:
        path.stat()
        with os.scandir(path) as iterator:
            next(iterator, None)
    except PermissionError as exc:
        raise PermissionError(describe_vault_permission_error(path)) from exc


def normalize_vault_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"Vault path does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"Vault path is not a directory: {path}")
    return path


def normalize_relative_path(raw_path: str, *, allow_root: bool = False) -> Path:
    text = (raw_path or "").strip()
    if not text or text == "/":
        if allow_root:
            return Path(".")
        raise ValueError("Path is required")

    rel = PurePosixPath(text)
    if rel.is_absolute():
        rel = PurePosixPath(*rel.parts[1:])

    parts = [part for part in rel.parts if part not in ("", ".")]
    if not parts and allow_root:
        return Path(".")
    if any(part == ".." for part in parts):
        raise ValueError("Path must stay within the vault root")
    return Path(*parts)


def resolve_path_inside_vault(root: Path, raw_path: str, *, allow_root: bool = False) -> Path:
    rel = normalize_relative_path(raw_path, allow_root=allow_root)
    try:
        return resolve_path_within(root, str(rel), label="Path")
    except ValueError as exc:
        raise ValueError("Path escapes the vault root") from exc


class VaultBridge:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        ensure_vault_access(self.root)

    def health(self) -> dict[str, Any]:
        return {"ok": True, "vault_path": str(self.root)}

    def list_files(self, directory: str = "/") -> list[str]:
        target = resolve_path_inside_vault(self.root, directory, allow_root=True)
        if not target.exists() or not target.is_dir():
            return []

        results: list[str] = []
        for entry in sorted(target.iterdir()):
            if entry.name.startswith("."):
                continue
            rel = entry.relative_to(self.root).as_posix()
            if entry.is_dir():
                results.append(rel + "/")
            else:
                results.append(rel)
        return results

    def read_note(self, file_path: str) -> dict[str, Any]:
        full = resolve_path_inside_vault(self.root, file_path)
        if not full.is_file():
            raise FileNotFoundError(f"Not found: {file_path}")
        content = full.read_text(encoding="utf-8")
        stat = full.stat()
        return {
            "content": content,
            "frontmatter": None,
            "tags": None,
            "stat": {
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
                "ctime": int(stat.st_ctime),
            },
        }

    def write_note(self, file_path: str, content: str, *, append: bool = False) -> dict[str, Any]:
        full = resolve_path_inside_vault(self.root, file_path)
        full.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with full.open("a", encoding="utf-8") as handle:
                handle.write(content)
        else:
            full.write_text(content, encoding="utf-8")
        stat = full.stat()
        return {
            "path": full.relative_to(self.root).as_posix(),
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
        }

    def delete_note(self, file_path: str) -> None:
        full = resolve_path_inside_vault(self.root, file_path)
        if not full.is_file():
            raise FileNotFoundError(f"Not found: {file_path}")
        full.unlink()

    def search(self, query: str, context_length: int = 100) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        query_lower = query.lower()
        for md_file in self.root.rglob("*.md"):
            rel = md_file.relative_to(self.root)
            if any(part.startswith(".") for part in rel.parts):
                continue
            try:
                safe_file = resolve_path_inside_vault(self.root, rel.as_posix())
                text = safe_file.read_text(encoding="utf-8")
            except (OSError, UnicodeError, ValueError):
                continue
            text_lower = text.lower()
            idx = text_lower.find(query_lower)
            if idx == -1:
                continue
            matches: list[dict[str, Any]] = []
            search_from = 0
            while True:
                pos = text_lower.find(query_lower, search_from)
                if pos == -1:
                    break
                start = max(0, pos - context_length)
                end = min(len(text), pos + len(query) + context_length)
                matches.append(
                    {
                        "match": {"start": pos, "end": pos + len(query)},
                        "context": text[start:end],
                    }
                )
                search_from = pos + 1
            results.append({"filename": rel.as_posix(), "matches": matches})
        return results


def _make_handler(bridge: VaultBridge, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "truffile-obsidian-bridge/0.1"

        def log_message(self, fmt: str, *args: object) -> None:
            logger.info("%s - %s", self.address_string(), fmt % args)

        def _require_auth(self) -> bool:
            expected = f"Bearer {token}"
            actual = self.headers.get("Authorization", "")
            if actual == expected:
                return True
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
            return False

        def _read_text_body(self) -> str:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b""
            return raw.decode("utf-8")

        def _read_json_body(self) -> dict[str, Any]:
            text = self._read_text_body()
            if not text:
                return {}
            return json.loads(text)

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _handle_exception(self, exc: Exception) -> None:
            if isinstance(exc, FileNotFoundError):
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            if isinstance(exc, PermissionError):
                self._send_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
                return
            if isinstance(exc, ValueError):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            logger.exception("Bridge request failed")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_GET(self) -> None:  # noqa: N802
            if not self._require_auth():
                return

            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            try:
                if parsed.path == "/health":
                    self._send_json(HTTPStatus.OK, bridge.health())
                    return
                if parsed.path == "/files":
                    directory = params.get("directory", ["/"])[0]
                    self._send_json(HTTPStatus.OK, {"files": bridge.list_files(directory)})
                    return
                if parsed.path == "/note":
                    file_path = params.get("path", [""])[0]
                    self._send_json(HTTPStatus.OK, bridge.read_note(file_path))
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            except Exception as exc:
                self._handle_exception(exc)

        def do_PUT(self) -> None:  # noqa: N802
            if not self._require_auth():
                return
            parsed = urlparse(self.path)
            if parsed.path != "/note":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            params = parse_qs(parsed.query)
            file_path = params.get("path", [""])[0]
            try:
                result = bridge.write_note(file_path, self._read_text_body(), append=False)
                self._send_json(HTTPStatus.OK, result)
            except Exception as exc:
                self._handle_exception(exc)

        def do_POST(self) -> None:  # noqa: N802
            if not self._require_auth():
                return
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/note":
                    params = parse_qs(parsed.query)
                    file_path = params.get("path", [""])[0]
                    result = bridge.write_note(file_path, self._read_text_body(), append=True)
                    self._send_json(HTTPStatus.OK, result)
                    return
                if parsed.path == "/search":
                    body = self._read_json_body()
                    query = str(body.get("query", "")).strip()
                    if not query:
                        raise ValueError("Query is required")
                    context_length = int(body.get("context_length", 100))
                    self._send_json(
                        HTTPStatus.OK,
                        {"results": bridge.search(query, context_length=context_length)},
                    )
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            except Exception as exc:
                self._handle_exception(exc)

        def do_DELETE(self) -> None:  # noqa: N802
            if not self._require_auth():
                return
            parsed = urlparse(self.path)
            if parsed.path != "/note":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            params = parse_qs(parsed.query)
            file_path = params.get("path", [""])[0]
            try:
                bridge.delete_note(file_path)
                self._send_json(HTTPStatus.OK, {"deleted": file_path})
            except Exception as exc:
                self._handle_exception(exc)

    return Handler


def build_server(config: ObsidianBridgeConfig) -> ThreadingHTTPServer:
    bridge = VaultBridge(config.vault_path)
    server = ThreadingHTTPServer((config.bind_host, config.port), _make_handler(bridge, config.token))
    return server
