from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AuthProvider(Protocol):
    def is_authenticated(self) -> bool: ...

    def verify(self) -> tuple[bool, str]: ...


class OAuthProvider(AuthProvider, Protocol):
    def get_access_token(self) -> str | None: ...

    def get_auth_headers(self) -> dict[str, str]: ...

    def refresh_if_needed(self) -> bool: ...


class ApiKeyProvider(AuthProvider, Protocol):
    def get_auth_headers(self, method: str, path: str) -> dict[str, str]: ...


class BrowserSessionProvider(AuthProvider, Protocol):
    async def connect(self) -> bool: ...

    async def disconnect(self) -> None: ...

    async def is_logged_in(self) -> bool: ...

    def cookies_for_httpx(self) -> Any: ...

    def get_default_headers(self, accept: str = "application/json") -> dict[str, str]: ...


@runtime_checkable
class HttpResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def is_success(self) -> bool: ...

    @property
    def text(self) -> str: ...

    @property
    def url(self) -> str: ...

    def json(self) -> Any: ...

    def raise_for_status(self) -> None: ...


@runtime_checkable
class HttpTransport(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> HttpResponse: ...

    async def close(self) -> None: ...


@runtime_checkable
class TokenStore(Protocol):
    def load(self) -> dict[str, Any] | None: ...

    def save(self, data: dict[str, Any]) -> None: ...

    def delete(self) -> None: ...


@runtime_checkable
class CookieStore(Protocol):
    def load_cookies(self) -> list[dict[str, Any]]: ...

    def save_cookies(self, cookies: list[dict[str, Any]]) -> None: ...

    def load_metadata(self) -> dict[str, Any] | None: ...

    def save_metadata(self, data: dict[str, Any]) -> None: ...

    def clear(self) -> None: ...
