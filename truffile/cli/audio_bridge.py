from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlparse


logger = logging.getLogger("truffile.audio_bridge")

MAX_AUDIO_BYTES = 100 * 1024 * 1024
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_CURRENT_PLAYER: subprocess.Popen[bytes] | None = None


@dataclass(frozen=True)
class AudioBridgeConfig:
    cache_path: Path
    token: str
    bind_host: str
    advertise_host: str
    port: int


def normalize_cache_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError(f"Audio cache path is not a directory: {path}")
    probe = path / ".truffile-audio-write-test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except PermissionError as exc:
        raise PermissionError(f"Permission denied for audio cache path: {path}") from exc
    return path


def _safe_filename(raw_name: str, fallback: str = "audio.mp3") -> str:
    name = Path(raw_name or fallback).name
    name = SAFE_NAME_RE.sub("_", name).strip("._")
    return name or fallback


def _resolve_cache_file(root: Path, raw_name: str) -> Path:
    name = _safe_filename(raw_name)
    rel = PurePosixPath(name)
    if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
        raise ValueError("Audio filename must be a simple relative filename")
    candidate = (root / name).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Audio filename escapes the cache directory")
    return candidate


def _unique_path(root: Path, raw_name: str) -> Path:
    target = _resolve_cache_file(root, raw_name)
    if not target.exists():
        return target
    stem = target.stem or "audio"
    suffix = target.suffix or ".mp3"
    for idx in range(1, 1000):
        candidate = root / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate a unique filename for {target.name}")


def _guess_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".ogg":
        return "audio/ogg"
    if suffix == ".flac":
        return "audio/flac"
    if suffix == ".m4a":
        return "audio/mp4"
    if suffix == ".opus":
        return "audio/opus"
    return "audio/mpeg"


class AudioBridge:
    def __init__(self, root: Path) -> None:
        self.root = normalize_cache_path(str(root))

    def health(self) -> dict[str, Any]:
        return {"ok": True, "cache_path": str(self.root)}

    def list_files(self) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        for path in sorted(self.root.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
            if not path.is_file() or path.name.startswith("."):
                continue
            stat = path.stat()
            files.append(
                {
                    "filename": path.name,
                    "path": str(path),
                    "mime_type": _guess_mime(path),
                    "bytes": stat.st_size,
                    "mtime": int(stat.st_mtime),
                }
            )
        return files

    def save_audio(self, *, filename: str, data_base64: str, mime_type: str | None = None, play: bool = False) -> dict[str, Any]:
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except Exception as exc:
            raise ValueError("data_base64 must be valid base64 audio data") from exc
        if not raw:
            raise ValueError("Audio data is empty")
        if len(raw) > MAX_AUDIO_BYTES:
            raise ValueError(f"Audio payload is too large; max is {MAX_AUDIO_BYTES} bytes")

        target = _unique_path(self.root, filename)
        target.write_bytes(raw)
        result = {
            "filename": target.name,
            "path": str(target),
            "mime_type": mime_type or _guess_mime(target),
            "bytes": len(raw),
            "played": False,
            "playback": None,
        }
        if play:
            result["playback"] = play_audio_file(target)
            result["played"] = bool(result["playback"].get("started")) if isinstance(result["playback"], dict) else False
        return result

    def read_audio(self, filename: str) -> tuple[Path, bytes]:
        path = _resolve_cache_file(self.root, filename)
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {filename}")
        return path, path.read_bytes()

    def play_cached(self, filename: str) -> dict[str, Any]:
        path = _resolve_cache_file(self.root, filename)
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {filename}")
        result = play_audio_file(path)
        result["filename"] = path.name
        result["path"] = str(path)
        return result

    def stop_playback(self) -> dict[str, Any]:
        return stop_audio_playback()


def _candidate_player_commands(path: Path) -> list[list[str]]:
    configured = os.getenv("TRUFFILE_AUDIO_PLAYER", "").strip()
    if configured:
        return [configured.split() + [str(path)]]
    if sys.platform == "darwin" and shutil.which("afplay"):
        return [["afplay", str(path)]]
    if os.name == "nt":
        ps = shutil.which("powershell") or shutil.which("powershell.exe")
        if ps:
            return [[ps, "-NoProfile", "-Command", f"(New-Object Media.SoundPlayer {json.dumps(str(path))}).PlaySync();"]]
    candidates: list[list[str]] = []
    if shutil.which("pw-play"):
        candidates.append(["pw-play", str(path)])
    if shutil.which("paplay"):
        candidates.append(["paplay", str(path)])
    if shutil.which("ffplay"):
        candidates.append(["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", str(path)])
    if shutil.which("mpv"):
        candidates.append(["mpv", "--no-video", "--really-quiet", str(path)])
    if path.suffix.lower() == ".wav" and shutil.which("aplay"):
        candidates.append(["aplay", str(path)])
    return candidates


def play_audio_file(path: Path) -> dict[str, Any]:
    global _CURRENT_PLAYER
    stop_audio_playback()
    for command in _candidate_player_commands(path):
        try:
            _CURRENT_PLAYER = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"started": True, "command": command[0]}
        except Exception as exc:
            logger.info("audio player failed: %s: %r", command[0], exc)
    return {
        "started": False,
        "error": "No supported local audio player found. Install ffplay, mpv, pw-play, paplay, or configure TRUFFILE_AUDIO_PLAYER.",
    }


def stop_audio_playback() -> dict[str, Any]:
    global _CURRENT_PLAYER
    proc = _CURRENT_PLAYER
    if proc is None:
        return {"stopped": False, "message": "No tracked playback process is running"}
    if proc.poll() is not None:
        _CURRENT_PLAYER = None
        return {"stopped": False, "message": "Tracked playback process had already exited"}

    try:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)
        return {"stopped": True, "pid": proc.pid}
    finally:
        _CURRENT_PLAYER = None


def _make_handler(bridge: AudioBridge, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "truffile-audio-bridge/0.1"

        def log_message(self, fmt: str, *args: object) -> None:
            logger.info("%s - %s", self.address_string(), fmt % args)

        def _require_auth(self) -> bool:
            expected = f"Bearer {token}"
            actual = self.headers.get("Authorization", "")
            if actual == expected:
                return True
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized"})
            return False

        def _read_json_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b""
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(self, status: HTTPStatus, payload: bytes, *, mime_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _handle_exception(self, exc: Exception) -> None:
            if isinstance(exc, FileNotFoundError):
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            if isinstance(exc, PermissionError):
                self._send_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
                return
            if isinstance(exc, (ValueError, json.JSONDecodeError)):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            logger.exception("Audio bridge request failed")
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
                    self._send_json(HTTPStatus.OK, {"files": bridge.list_files()})
                    return
                if parsed.path == "/audio":
                    filename = params.get("filename", [""])[0]
                    path, data = bridge.read_audio(filename)
                    self._send_bytes(HTTPStatus.OK, data, mime_type=_guess_mime(path))
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            except Exception as exc:
                self._handle_exception(exc)

        def do_POST(self) -> None:  # noqa: N802
            if not self._require_auth():
                return
            parsed = urlparse(self.path)
            try:
                body = self._read_json_body()
                if parsed.path == "/audio":
                    result = bridge.save_audio(
                        filename=str(body.get("filename", "")),
                        data_base64=str(body.get("data_base64", "")),
                        mime_type=body.get("mime_type"),
                        play=bool(body.get("play", False)),
                    )
                    self._send_json(HTTPStatus.OK, result)
                    return
                if parsed.path == "/play":
                    filename = str(body.get("filename", ""))
                    self._send_json(HTTPStatus.OK, bridge.play_cached(filename))
                    return
                if parsed.path == "/stop":
                    self._send_json(HTTPStatus.OK, bridge.stop_playback())
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            except Exception as exc:
                self._handle_exception(exc)

    return Handler


def build_server(config: AudioBridgeConfig) -> ThreadingHTTPServer:
    bridge = AudioBridge(config.cache_path)
    return ThreadingHTTPServer((config.bind_host, config.port), _make_handler(bridge, config.token))
