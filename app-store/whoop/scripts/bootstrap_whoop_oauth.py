#!/usr/bin/env python3
"""Bootstrap WHOOP OAuth locally and print Truffle deploy prompt values."""

from __future__ import annotations

import json
import os
import queue
import secrets
import subprocess
import threading
import time
import urllib.parse
import webbrowser
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR / ".env"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:8765/callback"
AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
PROFILE_URL = "https://api.prod.whoop.com/developer/v2/user/profile/basic"
SCOPES = (
    "offline",
    "read:profile",
    "read:body_measurement",
    "read:cycles",
    "read:recovery",
    "read:sleep",
    "read:workout",
)
CALLBACK_TIMEOUT_SECONDS = 180


@dataclass(frozen=True, slots=True)
class BootstrapConfig:
    client_id: str
    client_secret: str
    redirect_uri: str = DEFAULT_REDIRECT_URI


@dataclass(frozen=True, slots=True)
class OAuthCallback:
    code: str
    state: str
    error: str = ""
    error_description: str = ""


def _decode_quoted_env_value(value: str, quote: str) -> str:
    chars: list[str] = []
    escaped = False
    for char in value[1:]:
        if escaped:
            if quote == '"' and char == "n":
                chars.append("\n")
            elif quote == '"' and char == "r":
                chars.append("\r")
            elif quote == '"' and char == "t":
                chars.append("\t")
            else:
                chars.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == quote:
            return "".join(chars)
        chars.append(char)
    return "".join(chars)


def _strip_unquoted_env_comment(value: str) -> str:
    for index, char in enumerate(value):
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.rstrip()


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        value = raw_value.strip()
        if value.startswith('"'):
            values[key] = _decode_quoted_env_value(value, '"')
        elif value.startswith("'"):
            values[key] = _decode_quoted_env_value(value, "'")
        else:
            values[key] = _strip_unquoted_env_comment(value)
    return values


def load_config(*, env: Mapping[str, str] = os.environ, env_file: Path = ENV_FILE) -> BootstrapConfig:
    file_values = parse_env_file(env_file)

    def get_value(name: str, default: str = "") -> str:
        value = str(env.get(name, "") or "").strip()
        if value:
            return value
        return str(file_values.get(name, default) or "").strip()

    config = BootstrapConfig(
        client_id=get_value("WHOOP_CLIENT_ID"),
        client_secret=get_value("WHOOP_CLIENT_SECRET"),
        redirect_uri=get_value("WHOOP_REDIRECT_URI", DEFAULT_REDIRECT_URI),
    )

    missing = [
        name
        for name, value in (
            ("WHOOP_CLIENT_ID", config.client_id),
            ("WHOOP_CLIENT_SECRET", config.client_secret),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Missing required WHOOP OAuth setting(s): "
            f"{', '.join(missing)}. Create {env_file} from .env.example or export them in your shell."
        )

    return config


def generate_state() -> str:
    return secrets.token_hex(4)


def build_authorization_url(*, state: str, config: BootstrapConfig) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": " ".join(SCOPES),
            "state": state,
        }
    )
    return f"{AUTH_URL}?{query}"


def exchange_authorization_code(
    code: str,
    *,
    config: BootstrapConfig,
    curl_runner: Any = subprocess.run,
    now: float | None = None,
) -> dict[str, Any]:
    raw = _curl_form_json(
        TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": config.redirect_uri,
        },
        error_prefix="WHOOP token exchange failed",
        curl_runner=curl_runner,
    )

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("WHOOP token exchange returned a non-object payload")

    access_token = str(data.get("access_token", "") or "").strip()
    refresh_token = str(data.get("refresh_token", "") or "").strip()
    if not access_token or not refresh_token:
        raise RuntimeError("WHOOP token exchange did not return both access and refresh tokens")

    expires_in = int(data.get("expires_in", 0) or 0)
    data["expires_at"] = int((now if now is not None else time.time()) + expires_in)
    data["scope"] = str(data.get("scope", "") or "").strip()
    data["token_type"] = str(data.get("token_type", "bearer") or "bearer").strip() or "bearer"
    return data


def fetch_profile(
    access_token: str,
    *,
    curl_runner: Any = subprocess.run,
) -> dict[str, Any]:
    raw = _curl_json(
        [
            "curl",
            "-sS",
            "--fail-with-body",
            "--max-time",
            "30",
            "-H",
            "Accept: application/json",
            "-H",
            f"Authorization: Bearer {access_token}",
            PROFILE_URL,
        ],
        error_prefix="WHOOP profile smoke test failed",
        curl_runner=curl_runner,
    )

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("WHOOP profile smoke test returned a non-object payload")
    return payload


def _curl_form_json(
    url: str,
    form: dict[str, str],
    *,
    error_prefix: str,
    curl_runner: Any = subprocess.run,
) -> str:
    command = [
        "curl",
        "-sS",
        "--fail-with-body",
        "--max-time",
        "30",
        "-X",
        "POST",
        "-H",
        "Accept: application/json",
    ]
    for key, value in form.items():
        command.extend(["--data-urlencode", f"{key}={value}"])
    command.append(url)
    return _curl_json(command, error_prefix=error_prefix, curl_runner=curl_runner)


def _curl_json(
    command: list[str],
    *,
    error_prefix: str,
    curl_runner: Any = subprocess.run,
) -> str:
    try:
        result = curl_runner(command, capture_output=True, text=True, timeout=35, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("curl is required to run the WHOOP OAuth bootstrap script") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{error_prefix}: curl timed out") from exc

    stdout = str(getattr(result, "stdout", "") or "")
    stderr = str(getattr(result, "stderr", "") or "")
    returncode = int(getattr(result, "returncode", 1) or 0)
    if returncode != 0:
        detail = (stdout or stderr).strip()
        suffix = f": {detail[:300]}" if detail else ""
        raise RuntimeError(f"{error_prefix}: curl exited {returncode}{suffix}")
    return stdout


def prompt_values(token_payload: dict[str, Any], *, config: BootstrapConfig) -> list[tuple[str, str]]:
    return [
        ("WHOOP Client ID", config.client_id),
        ("WHOOP Client Secret", config.client_secret),
        ("WHOOP Redirect URI", config.redirect_uri),
        ("WHOOP Access Token", str(token_payload["access_token"])),
        ("WHOOP Refresh Token", str(token_payload["refresh_token"])),
        ("WHOOP Access Token Expires At", str(token_payload["expires_at"])),
        ("WHOOP Token Scope", str(token_payload.get("scope", "") or "")),
        ("WHOOP Token Type", str(token_payload.get("token_type", "bearer") or "bearer")),
    ]


def render_prompt_values(token_payload: dict[str, Any], *, config: BootstrapConfig) -> str:
    lines = ["Paste these values into the matching `truffile deploy` prompts:"]
    for label, value in prompt_values(token_payload, config=config):
        lines.append(f"{label}:")
        lines.append(value)
    return "\n".join(lines)


class OAuthCallbackServer:
    def __init__(self, *, redirect_uri: str) -> None:
        parsed = urllib.parse.urlparse(redirect_uri)
        self._expected_path = parsed.path or "/"
        self._events: queue.Queue[OAuthCallback] = queue.Queue(maxsize=1)
        handler_cls = self._build_handler()
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        try:
            self._server = ThreadingHTTPServer((host, port), handler_cls)
        except OSError as exc:
            raise RuntimeError(
                f"Could not bind the local WHOOP callback server on {host}:{port}. "
                "Make sure the redirect URI is free and another process is not already using that port."
            ) from exc
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def wait_for_callback(self, *, timeout: float) -> OAuthCallback:
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError(f"Timed out waiting for WHOOP OAuth redirect after {int(timeout)} seconds") from exc

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != outer._expected_path:
                    self.send_error(404, "Unexpected callback path")
                    return

                params = urllib.parse.parse_qs(parsed.query)
                callback = OAuthCallback(
                    code=str(params.get("code", [""])[0] or "").strip(),
                    state=str(params.get("state", [""])[0] or "").strip(),
                    error=str(params.get("error", [""])[0] or "").strip(),
                    error_description=str(params.get("error_description", [""])[0] or "").strip(),
                )
                if outer._events.empty():
                    outer._events.put(callback)

                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                if callback.error:
                    message = "WHOOP authorization failed. You can close this window."
                else:
                    message = "WHOOP authorization received. You can close this window and return to the terminal."
                self.wfile.write(message.encode("utf-8"))

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
                return None

        return Handler


def authorize_and_print_env(*, open_browser: bool = True) -> int:
    config = load_config()
    state = generate_state()
    auth_url = build_authorization_url(state=state, config=config)
    server = OAuthCallbackServer(redirect_uri=config.redirect_uri)
    server.start()
    try:
        print("Before continuing, make sure this redirect URI is saved in the WHOOP dashboard:", flush=True)
        print(f"  {config.redirect_uri}", flush=True)
        print("Click Update App after adding it; an unsaved redirect will be rejected.", flush=True)
        print(flush=True)
        print(
            "The authorization URL includes the OAuth request scope 'offline' so WHOOP returns a refresh token. "
            "It may not appear as a dashboard checkbox.",
            flush=True,
        )
        print(flush=True)
        print("WHOOP authorization URL:", flush=True)
        print(auth_url, flush=True)
        print(flush=True)

        if open_browser:
            try:
                webbrowser.open(auth_url)
            except Exception:
                pass

        callback = server.wait_for_callback(timeout=CALLBACK_TIMEOUT_SECONDS)
        if callback.error:
            description = f": {callback.error_description}" if callback.error_description else ""
            raise RuntimeError(f"WHOOP authorization failed with error '{callback.error}'{description}")
        if not callback.code:
            raise RuntimeError("WHOOP redirect did not include an authorization code")
        if callback.state != state:
            raise RuntimeError("WHOOP redirect state did not match the request state")

        token_payload = exchange_authorization_code(callback.code, config=config)
        profile = fetch_profile(str(token_payload["access_token"]))
        print(
            f"WHOOP OAuth OK for user_id={profile.get('user_id')} email={profile.get('email')}",
            flush=True,
        )
        print(flush=True)
        print("Run `truffile deploy ./app-store/whoop` and paste the generated values when prompted.", flush=True)
        print("Do not commit these token values.", flush=True)
        print(flush=True)
        print(render_prompt_values(token_payload, config=config), flush=True)
        return 0
    finally:
        server.close()


def main() -> int:
    if "BROWSER" in os.environ and os.environ["BROWSER"].strip().lower() == "none":
        return authorize_and_print_env(open_browser=False)
    return authorize_and_print_env(open_browser=True)


if __name__ == "__main__":
    raise SystemExit(main())
