from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from truffile.transport.client import TruffleClient

from .env import build_env_prefix


def _compact_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value not in (None, "", [], {})}


def _scope_string(scopes: Any) -> str:
    if isinstance(scopes, str):
        return scopes.strip()
    if isinstance(scopes, list):
        return " ".join(str(scope).strip() for scope in scopes if str(scope).strip())
    return ""


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _new_pkce_pair() -> tuple[str, str]:
    verifier = _base64url(secrets.token_bytes(32))
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _first_value(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key, "") or "").strip()
        if value:
            return value
    return ""


async def _fetch_json(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    resp = await client.get(url, timeout=30.0)
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, dict) else {}


async def _discover_oauth_metadata(
    client: httpx.AsyncClient,
    step: dict[str, Any],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    resource_metadata_endpoint = str(step.get("resource_metadata_endpoint", "") or "").strip()
    if resource_metadata_endpoint:
        metadata.update(await _fetch_json(client, resource_metadata_endpoint))

    auth_servers = metadata.get("authorization_servers")
    if isinstance(auth_servers, list) and auth_servers:
        issuer = str(auth_servers[0] or "").rstrip("/")
        if issuer:
            for suffix in (
                "/.well-known/oauth-authorization-server",
                "/.well-known/openid-configuration",
            ):
                try:
                    metadata.update(await _fetch_json(client, f"{issuer}{suffix}"))
                    break
                except Exception:
                    continue

    return metadata


async def _register_dynamic_client(
    client: httpx.AsyncClient,
    step: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    registration_endpoint = _first_value(metadata, "registration_endpoint")
    if not registration_endpoint:
        raise RuntimeError("OAuth dynamic client registration requested, but no registration_endpoint was discovered")

    scopes = _scope_string(step.get("scopes"))
    body = _compact_dict(
        {
            "client_name": step.get("client_name") or "Truffle",
            "redirect_uris": [step["redirect_uri"]],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none" if not step.get("client_secret") else "client_secret_post",
            "scope": scopes,
        }
    )
    resp = await client.post(registration_endpoint, json=body, timeout=30.0)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict) or not str(payload.get("client_id", "") or "").strip():
        raise RuntimeError("OAuth dynamic client registration did not return client_id")
    return payload


def _build_authorization_url(
    *,
    auth_endpoint: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: Any = None,
    oauth_resource: str = "",
    prompt: str | None = None,
    access_type: str | None = None,
    include_granted_scopes: bool | None = None,
    code_challenge: str = "",
) -> str:
    query: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    scope = _scope_string(scopes)
    if scope:
        query["scope"] = scope
    if oauth_resource:
        query["resource"] = oauth_resource
    if prompt:
        query["prompt"] = prompt
    if access_type:
        query["access_type"] = access_type
    if include_granted_scopes is not None:
        query["include_granted_scopes"] = "true" if include_granted_scopes else "false"
    if code_challenge:
        query["code_challenge"] = code_challenge
        query["code_challenge_method"] = "S256"
    separator = "&" if "?" in auth_endpoint else "?"
    return f"{auth_endpoint}{separator}{urlencode(query)}"


def _parse_callback(value: str, *, expected_state: str) -> str:
    raw = value.strip()
    if not raw:
        raise RuntimeError("OAuth callback URL/code is required")
    if "://" not in raw and "code=" not in raw:
        return raw
    parsed = urlparse(raw)
    params = parse_qs(parsed.query or parsed.fragment)
    error = (params.get("error") or [""])[0]
    if error:
        description = (params.get("error_description") or [""])[0]
        raise RuntimeError(f"OAuth provider returned error: {error}" + (f" - {description}" if description else ""))
    state = (params.get("state") or [""])[0]
    if expected_state and state and state != expected_state:
        raise RuntimeError("OAuth callback state did not match; aborting install")
    code = (params.get("code") or [""])[0]
    if not code:
        raise RuntimeError("OAuth callback did not include code")
    return code


async def _exchange_authorization_code(
    client: httpx.AsyncClient,
    *,
    token_endpoint: str,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str = "",
    oauth_resource: str = "",
    code_verifier: str = "",
) -> dict[str, Any]:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    if client_secret:
        form["client_secret"] = client_secret
    if oauth_resource:
        form["resource"] = oauth_resource
    if code_verifier:
        form["code_verifier"] = code_verifier

    resp = await client.post(
        token_endpoint,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, dict) or not str(payload.get("access_token", "") or "").strip():
        raise RuntimeError("OAuth token response did not include access_token")
    return payload


def _build_installed_token_payload(
    *,
    token_response: dict[str, Any],
    step: dict[str, Any],
    client_registration: dict[str, Any],
    client_id: str,
    client_secret: str,
    auth_endpoint: str,
    token_endpoint: str,
    oauth_resource: str,
) -> dict[str, Any]:
    now = int(time.time())
    payload = dict(token_response)
    payload.update(
        _compact_dict(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": step.get("redirect_uri"),
                "auth_endpoint": auth_endpoint,
                "token_endpoint": token_endpoint,
                "resource": oauth_resource,
                "oauth_resource": oauth_resource,
                "scope": payload.get("scope") or _scope_string(step.get("scopes")),
                "created_at": now,
            }
        )
    )
    if "expires_in" in payload and "expires_at" not in payload:
        try:
            payload["expires_at"] = now + int(payload["expires_in"])
        except (TypeError, ValueError):
            pass
    for key in ("client_id_issued_at", "client_secret_expires_at", "registration_client_uri"):
        if key in client_registration and key not in payload:
            payload[key] = client_registration[key]
    return payload


async def _write_json_file(client: TruffleClient, *, path: str, payload: dict[str, Any]) -> None:
    encoded = base64.b64encode((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii")
    quoted_path = repr(path)
    script = f"""
python - <<'PY'
import base64
from pathlib import Path
path = Path({quoted_path})
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(base64.b64decode({encoded!r}))
path.chmod(0o600)
PY
""".strip()
    result = await client.exec(script, cwd="/")
    if result.exit_code != 0:
        raise RuntimeError(f"Failed to write OAuth token file {path}: exit code {result.exit_code}")


async def _run_update_check(
    step: dict[str, Any],
    *,
    client: TruffleClient,
    exec_cwd: str,
    info: Callable[[str], None],
    error: Callable[[str], None],
    scrolling_log_cls: Any,
    collected_env: dict[str, str],
) -> None:
    update_check = str(step.get("update_check", "") or "").strip()
    if not update_check:
        return
    update_check = f"{build_env_prefix(collected_env)}{update_check}"
    info("Validating OAuth...")
    log = scrolling_log_cls(height=4, prefix="  ")
    exit_code = 0
    async for ev, data in client.exec_stream(update_check, cwd=exec_cwd):
        if ev == "log":
            try:
                line = json.loads(data).get("line", "")
            except Exception:
                line = data
            log.add(line)
        elif ev == "exit":
            try:
                exit_code = int(json.loads(data).get("code", 0))
            except (ValueError, KeyError):
                pass
    log.finish()
    if exit_code != 0:
        error("OAuth validation failed. Check the account authorization and try again.")
        raise RuntimeError("OAuth validation failed")


async def handle_oauth(
    step: dict[str, Any],
    *,
    client: TruffleClient,
    exec_cwd: str,
    info: Callable[[str], None],
    error: Callable[[str], None],
    scrolling_log_cls: Any,
    collected_env: dict[str, str],
    **_kw: Any,
) -> None:
    step_name = str(step.get("name") or "OAuth Sign-In")
    provider = str(step.get("provider") or "OAuth provider")
    description = str(step.get("description") or "").strip()
    redirect_uri = str(step.get("redirect_uri") or "").strip()
    if not redirect_uri:
        raise RuntimeError(f"{step_name}: redirect_uri is required")

    info(step_name)
    if description:
        print(description)

    async with httpx.AsyncClient() as http:
        metadata = await _discover_oauth_metadata(http, step)
        auth_endpoint = str(step.get("auth_endpoint") or metadata.get("authorization_endpoint") or "").strip()
        token_endpoint = str(step.get("token_endpoint") or metadata.get("token_endpoint") or "").strip()
        if not auth_endpoint or not token_endpoint:
            raise RuntimeError(f"{step_name}: auth_endpoint and token_endpoint are required")

        client_registration: dict[str, Any] = {}
        if bool(step.get("dynamic_client_registration")):
            client_registration = await _register_dynamic_client(http, step, metadata)

        client_id = str(step.get("client_id") or client_registration.get("client_id") or "").strip()
        client_secret = str(step.get("client_secret") or client_registration.get("client_secret") or "").strip()
        if not client_id:
            raise RuntimeError(f"{step_name}: OAuth client_id is required")

        use_pkce = bool(step.get("pkce")) or (bool(step.get("dynamic_client_registration")) and not client_secret)
        code_verifier = ""
        code_challenge = ""
        if use_pkce:
            code_verifier, code_challenge = _new_pkce_pair()
        state = secrets.token_urlsafe(24)
        oauth_resource = str(step.get("oauth_resource") or metadata.get("resource") or metadata.get("resource_name") or "").strip()
        auth_url = _build_authorization_url(
            auth_endpoint=auth_endpoint,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            scopes=step.get("scopes"),
            oauth_resource=oauth_resource,
            prompt=step.get("prompt"),
            access_type=step.get("access_type"),
            include_granted_scopes=step.get("include_granted_scopes"),
            code_challenge=code_challenge,
        )

        print()
        print(f"Open this {provider} authorization URL:")
        print(auth_url)
        callback = input("  Paste the callback URL or authorization code: ")
        code = _parse_callback(callback, expected_state=state)

        token_response = await _exchange_authorization_code(
            http,
            token_endpoint=token_endpoint,
            code=code,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret=client_secret,
            oauth_resource=oauth_resource,
            code_verifier=code_verifier,
        )

    token_file = str(step.get("token_output_file") or "").strip()
    token_file_env = str(step.get("token_file_env_name") or "").strip()
    if not token_file:
        raise RuntimeError(f"{step_name}: token_output_file is required")
    if not token_file_env:
        raise RuntimeError(f"{step_name}: token_file_env_name is required")

    installed_payload = _build_installed_token_payload(
        token_response=token_response,
        step=step,
        client_registration=client_registration,
        client_id=client_id,
        client_secret=client_secret,
        auth_endpoint=auth_endpoint,
        token_endpoint=token_endpoint,
        oauth_resource=oauth_resource,
    )
    await _write_json_file(client, path=token_file, payload=installed_payload)
    collected_env[token_file_env] = token_file
    client_id_env = str(step.get("client_id_env") or "").strip()
    client_secret_env = str(step.get("client_secret_env") or "").strip()
    if client_id_env:
        collected_env[client_id_env] = client_id
    if client_secret_env and client_secret:
        collected_env[client_secret_env] = client_secret
    await _run_update_check(
        step,
        client=client,
        exec_cwd=exec_cwd,
        info=info,
        error=error,
        scrolling_log_cls=scrolling_log_cls,
        collected_env=collected_env,
    )
    info(f"{provider} OAuth configured")
