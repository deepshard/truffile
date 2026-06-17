"""Thin async WHOOP client with token refresh support."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from truffile.app_runtime import AppAuthError, AppRuntimeFailure, HttpTransport

from config import WhoopConfig
from whoop_auth import WhoopOAuth


class WhoopApiError(AppRuntimeFailure):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        response_text: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class _HttpxTransport:
    def __init__(self, *, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        return await self._client.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json,
            headers=headers,
            content=content,
        )

    async def close(self) -> None:
        await self._client.aclose()


def _mask_token(token: str) -> str:
    cleaned = token.strip()
    if len(cleaned) <= 8:
        return cleaned[:2] + "..." if cleaned else "none"
    return f"{cleaned[:4]}...{cleaned[-4:]}"


class WhoopClient:
    def __init__(
        self,
        *,
        config: WhoopConfig | None = None,
        auth: WhoopOAuth | None = None,
        http: HttpTransport | None = None,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._config = config or WhoopConfig.from_env()
        self._time_fn = time_fn or time.time
        self._auth = auth or WhoopOAuth(self._config, time_fn=self._time_fn)
        self._http = http or _HttpxTransport()
        self._refresh_lock = asyncio.Lock()

    @property
    def auth(self) -> WhoopOAuth:
        return self._auth

    async def close(self) -> None:
        try:
            await self._http.close()
        except Exception:
            pass

    async def verify(self) -> tuple[bool, str]:
        errors = self._auth.config_errors()
        if errors:
            return False, "; ".join(errors)
        try:
            profile = await self.get_profile_basic()
        except AppAuthError as exc:
            return False, f"WHOOP verification failed: {exc}"
        except WhoopApiError as exc:
            if exc.status_code:
                return False, f"WHOOP verification failed: HTTP {exc.status_code} {exc}"
            return False, f"WHOOP verification failed: {exc}"
        except Exception as exc:
            return False, f"WHOOP verification failed: {exc}"

        masked = _mask_token(self._auth.get_access_token())
        return True, (
            "WHOOP credentials verified. "
            f"user_id={profile.get('user_id')} "
            f"email={profile.get('email')} "
            f"token={masked}"
        )

    async def get_profile_basic(self) -> dict[str, Any]:
        return await self._request("GET", "/v2/user/profile/basic")

    async def get_body_measurements(self) -> dict[str, Any]:
        return await self._request("GET", "/v2/user/measurement/body")

    async def list_cycles(
        self,
        *,
        limit: int | None = None,
        start: str | None = None,
        end: str | None = None,
        next_token: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v2/cycle",
            params={
                "limit": limit,
                "start": start,
                "end": end,
                "nextToken": next_token,
            },
        )

    async def get_cycle_by_id(self, cycle_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/v2/cycle/{cycle_id}")

    async def list_recovery(
        self,
        *,
        limit: int | None = None,
        start: str | None = None,
        end: str | None = None,
        next_token: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v2/recovery",
            params={
                "limit": limit,
                "start": start,
                "end": end,
                "nextToken": next_token,
            },
        )

    async def get_recovery_for_cycle(self, cycle_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/v2/cycle/{cycle_id}/recovery")

    async def list_sleep(
        self,
        *,
        limit: int | None = None,
        start: str | None = None,
        end: str | None = None,
        next_token: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v2/activity/sleep",
            params={
                "limit": limit,
                "start": start,
                "end": end,
                "nextToken": next_token,
            },
        )

    async def get_sleep_by_id(self, sleep_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v2/activity/sleep/{sleep_id}")

    async def get_sleep_for_cycle(self, cycle_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/v2/cycle/{cycle_id}/sleep")

    async def list_workouts(
        self,
        *,
        limit: int | None = None,
        start: str | None = None,
        end: str | None = None,
        next_token: str | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/v2/activity/workout",
            params={
                "limit": limit,
                "start": start,
                "end": end,
                "nextToken": next_token,
            },
        )

    async def get_workout_by_id(self, workout_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v2/activity/workout/{workout_id}")

    async def get_recent_summary(self) -> dict[str, Any]:
        profile = await self.get_profile_basic()
        body = await self.get_body_measurements()
        cycles = await self.list_cycles(limit=1)
        latest_cycle = self._first_record(cycles)
        latest_recovery = None
        latest_sleep = None
        if isinstance(latest_cycle, dict) and latest_cycle.get("id") is not None:
            cycle_id = int(latest_cycle["id"])
            latest_recovery = await self.get_recovery_for_cycle(cycle_id)
            latest_sleep = await self.get_sleep_for_cycle(cycle_id)
        workouts = await self.list_workouts(limit=3)
        return {
            "profile": profile,
            "body_measurements": body,
            "latest_cycle": latest_cycle,
            "latest_recovery": latest_recovery,
            "latest_sleep": latest_sleep,
            "recent_workouts": workouts.get("records", []),
            "recent_workouts_next_token": workouts.get("next_token"),
        }

    def auth_status(self) -> dict[str, Any]:
        return self._auth.status()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        retry_on_auth: bool = True,
    ) -> dict[str, Any]:
        if not self._auth.get_access_token() and self._auth.can_refresh():
            await self._refresh_access_token()

        if self._auth.token_expires_soon():
            await self._refresh_access_token()

        response = await self._send_request(method, path, params=params)
        if response.status_code == 401 and retry_on_auth:
            await self._refresh_access_token(force=True)
            response = await self._send_request(method, path, params=params)

        if response.status_code in {401, 403}:
            raise AppAuthError(
                "WHOOP rejected the installed credentials. Reinstall the app with fresh WHOOP tokens."
            )

        if not response.is_success:
            raise WhoopApiError(
                f"WHOOP API request failed for {path}",
                status_code=response.status_code,
                response_text=self._response_text(response),
            )

        data = response.json()
        if not isinstance(data, dict):
            raise AppRuntimeFailure(f"WHOOP API returned a non-object payload for {path}")
        return data

    async def _send_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> Any:
        clean_params = {key: value for key, value in (params or {}).items() if value is not None}
        headers = {
            "Accept": "application/json",
        }
        headers.update(self._auth.get_auth_headers())
        return await self._http.request(
            method.upper(),
            f"{self._config.api_base.rstrip('/')}{path}",
            params=clean_params or None,
            headers=headers,
        )

    async def _refresh_access_token(self, *, force: bool = False) -> dict[str, Any]:
        async with self._refresh_lock:
            if not force and self._auth.get_access_token() and not self._auth.token_expires_soon():
                payload = self._auth.get_oauth_payload()
                return payload if payload is not None else {}

            if not self._auth.can_refresh():
                raise AppAuthError(
                    "WHOOP refresh requires client_id, client_secret, and refresh_token in the installed OAuth token file."
                )

            refresh_payload = {
                "grant_type": "refresh_token",
                "refresh_token": self._auth.get_refresh_token(),
                "client_id": self._auth.get_client_id(),
                "client_secret": self._auth.get_client_secret(),
                "scope": "offline",
            }
            response = await self._http.request(
                "POST",
                self._config.token_url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                content=urlencode(refresh_payload),
            )

            if response.status_code in {401, 403}:
                raise AppAuthError(
                    "WHOOP token refresh failed. Check the client credentials and refresh token."
                )

            if not response.is_success:
                raise WhoopApiError(
                    "WHOOP token refresh failed",
                    status_code=response.status_code,
                    response_text=self._response_text(response),
                )

            data = response.json()
            if not isinstance(data, dict) or not str(data.get("access_token", "") or "").strip():
                raise AppRuntimeFailure("WHOOP token refresh returned an invalid payload")
            return self._auth.remember_token_response(data, now=self._time_fn())

    @staticmethod
    def _first_record(payload: dict[str, Any]) -> dict[str, Any] | None:
        records = payload.get("records")
        if not isinstance(records, list) or not records:
            return None
        first = records[0]
        return first if isinstance(first, dict) else None

    @staticmethod
    def _response_text(response: Any) -> str:
        try:
            return str(response.text or "")
        except Exception:
            return ""
