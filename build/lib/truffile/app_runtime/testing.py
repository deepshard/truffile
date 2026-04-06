from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import logging
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx

from .worker import LocalBackgroundContext
from .errors import ErrorEnvelope


@dataclass(slots=True)
class HarnessResult:
    success: bool
    logs: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    submissions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    contexts: list[LocalBackgroundContext] = field(default_factory=list)


@dataclass(slots=True)
class RecordedSubmission:
    text: str
    uris: list[str] = field(default_factory=list)
    priority: int = 0

    @classmethod
    def from_context_submission(cls, submission: Any) -> RecordedSubmission:
        return cls(
            text=str(getattr(submission, "text", "")),
            uris=list(getattr(submission, "uris", ()) or ()),
            priority=int(getattr(submission, "priority", 0)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "uris": list(self.uris),
            "priority": self.priority,
        }


@dataclass(slots=True)
class RecordedBackgroundError:
    error_type: int
    error_message: str
    needs_intervention: bool

    @classmethod
    def from_envelope(cls, envelope: ErrorEnvelope) -> RecordedBackgroundError:
        return cls(
            error_type=envelope.error_type,
            error_message=envelope.error_message,
            needs_intervention=envelope.needs_intervention,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "needs_intervention": self.needs_intervention,
        }


def make_background_ctx(app: Any, *, run_num: int = 0) -> LocalBackgroundContext:
    return app.run_once_for_test(run_num=run_num)


class FakeBackgroundRuntime:
    def __init__(self, app: Any, *, cycles: int = 1) -> None:
        self._app = app
        self.cycles = cycles
        self.contexts: list[LocalBackgroundContext] = []

    def run(self) -> list[LocalBackgroundContext]:
        self.contexts = [self._app.run_once_for_test(run_num=run_num) for run_num in range(self.cycles)]
        return list(self.contexts)

    @property
    def all_submissions(self) -> list[RecordedSubmission]:
        out: list[RecordedSubmission] = []
        for ctx in self.contexts:
            out.extend(RecordedSubmission.from_context_submission(submission) for submission in ctx.bg.submissions)
        return out

    @property
    def all_reported_errors(self) -> list[RecordedBackgroundError]:
        out: list[RecordedBackgroundError] = []
        for ctx in self.contexts:
            out.extend(RecordedBackgroundError.from_envelope(error) for error in ctx.app_runtime.errors)
        return out


@dataclass(slots=True)
class FakeHttpResponse:
    status_code: int = 200
    _json: Any = None
    _text: str = ""
    url: str = ""

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 400

    @property
    def text(self) -> str:
        return self._text

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if not self.is_success:
            request = httpx.Request("GET", self.url or "http://fake")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                f"Fake {self.status_code}",
                request=request,
                response=response,
            )


class FakeHttpTransport:
    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self._responses: dict[str, FakeHttpResponse] = {}
        self._calls: list[dict[str, Any]] = []
        for key, value in (responses or {}).items():
            self.add(key, value)

    def add(self, method_path: str, response: Any) -> None:
        if isinstance(response, FakeHttpResponse):
            self._responses[method_path] = response
        else:
            self._responses[method_path] = FakeHttpResponse(status_code=200, _json=response)

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> FakeHttpResponse:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") or "/"
        key = f"{method.upper()} {path}"
        self._calls.append(
            {
                "method": method.upper(),
                "url": url,
                "path": path,
                "params": params,
                "json": json,
                "headers": headers,
                "content": content,
            }
        )
        if key in self._responses:
            return self._responses[key]
        for registered, response in self._responses.items():
            if key.startswith(registered):
                return response
        raise KeyError(f"FakeHttpTransport: no response for {key!r}. Registered: {list(self._responses.keys())}")

    async def close(self) -> None:
        return None

    @property
    def calls(self) -> list[dict[str, Any]]:
        return list(self._calls)

    def reset(self) -> None:
        self._calls.clear()


class FakeAuthProvider:
    def __init__(self, *, authenticated: bool = True, verify_msg: str = "ok") -> None:
        self._authenticated = authenticated
        self._verify_msg = verify_msg

    def is_authenticated(self) -> bool:
        return self._authenticated

    def verify(self) -> tuple[bool, str]:
        return self._authenticated, self._verify_msg


class FakeApiKeyProvider(FakeAuthProvider):
    def __init__(self, *, authenticated: bool = True, headers: dict[str, str] | None = None) -> None:
        super().__init__(authenticated=authenticated)
        self._headers = headers or {"X-API-Key": "fake-key"}

    def get_auth_headers(self, method: str, path: str) -> dict[str, str]:
        if not self._authenticated:
            return {}
        return dict(self._headers)


class FakeOAuthProvider(FakeAuthProvider):
    def __init__(self, *, authenticated: bool = True, access_token: str = "fake-access-token") -> None:
        super().__init__(authenticated=authenticated)
        self._access_token = access_token

    def get_access_token(self) -> str | None:
        return self._access_token if self._authenticated else None

    def get_auth_headers(self) -> dict[str, str]:
        if not self._authenticated:
            return {}
        return {"Authorization": f"Bearer {self._access_token}"}

    def refresh_if_needed(self) -> bool:
        return self._authenticated


class _ListHandler(logging.Handler):
    def __init__(self, sink: list[str]) -> None:
        super().__init__()
        self._sink = sink
        self.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(self.format(record))


@contextmanager
def _capture_logs(logger_names: Iterable[str]) -> Any:
    log_lines: list[str] = []
    handler = _ListHandler(log_lines)
    attached: list[tuple[logging.Logger, bool, int]] = []

    for name in logger_names:
        logger = logging.getLogger(name)
        attached.append((logger, logger.propagate, logger.level))
        logger.addHandler(handler)
        logger.propagate = False
        if logger.level > logging.INFO:
            logger.setLevel(logging.INFO)

    try:
        yield log_lines
    finally:
        for logger, propagate, level in attached:
            logger.removeHandler(handler)
            logger.propagate = propagate
            logger.setLevel(level)


class AppHarness:
    def __init__(
        self,
        *,
        fg_app: Any | None = None,
        bg_app: Any | None = None,
        logger_names: Iterable[str] = (),
    ) -> None:
        self._fg_app = fg_app
        self._bg_app = bg_app
        self._logger_names = list(logger_names)

    async def run_fg(self, *, calls: list[tuple[str, dict[str, Any]]]) -> HarnessResult:
        if self._fg_app is None:
            raise RuntimeError("foreground app is not configured for this harness")

        logger_names = self._merged_logger_names(self._fg_app.logger_names())
        with _capture_logs(logger_names) as logs:
            tool_calls: list[dict[str, Any]] = []
            errors: list[str] = []
            success = True

            for tool_name, arguments in calls:
                try:
                    result = await self._fg_app.invoke_tool(tool_name, **arguments)
                    tool_calls.append(
                        {
                            "tool": tool_name,
                            "arguments": arguments,
                            "result": result,
                        }
                    )
                except Exception as exc:
                    success = False
                    message = f"{tool_name}: {exc}"
                    errors.append(message)
                    tool_calls.append(
                        {
                            "tool": tool_name,
                            "arguments": arguments,
                            "error": str(exc),
                        }
                    )

            return HarnessResult(
                success=success,
                logs=list(logs),
                tool_calls=tool_calls,
                errors=errors,
            )

    async def run_bg(self, *, cycles: int = 1) -> HarnessResult:
        if self._bg_app is None:
            raise RuntimeError("background app is not configured for this harness")

        logger_names = self._merged_logger_names(self._bg_app.logger_names())
        with _capture_logs(logger_names) as logs:
            runtime = FakeBackgroundRuntime(self._bg_app, cycles=cycles)
            contexts = runtime.run()
            submissions = [submission.as_dict() for submission in runtime.all_submissions]
            errors = [error.error_message for error in runtime.all_reported_errors]
            success = not errors

            return HarnessResult(
                success=success,
                logs=list(logs),
                submissions=submissions,
                errors=errors,
                contexts=contexts,
            )

    def _merged_logger_names(self, default_names: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for name in list(default_names) + self._logger_names:
            if name in seen:
                continue
            seen.add(name)
            merged.append(name)
        return merged
