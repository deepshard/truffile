from __future__ import annotations

from dataclasses import dataclass
import logging
import sys
from typing import Any, Generic, Iterable, TypeVar

from truffle.app.background_pb2 import BackgroundContext

from .errors import ErrorEnvelope, ErrorReporter

_PRIORITY_DEFAULT = getattr(
    BackgroundContext,
    "PRIORITY_DEFAULT",
    getattr(BackgroundContext, "PRIORITY_HIGH", 1),
)

WorkerT = TypeVar("WorkerT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class Submission:
    text: str
    uris: tuple[str, ...] = ()
    priority: int = _PRIORITY_DEFAULT

    def __init__(
        self,
        *,
        text: str,
        uris: Iterable[str] = (),
        priority: int = _PRIORITY_DEFAULT,
    ) -> None:
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "uris", tuple(uris))
        object.__setattr__(self, "priority", priority)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "uris": list(self.uris),
            "priority": self.priority,
        }


@dataclass(slots=True)
class _LocalRuntimeReporter:
    errors: list[ErrorEnvelope]

    def report_error(
        self,
        *,
        error_type: int,
        error_message: str,
        needs_intervention: bool = False,
        app_uuid: str | None = None,
    ) -> ErrorEnvelope:
        envelope = ErrorEnvelope(
            error_type=error_type,
            error_message=error_message,
            needs_intervention=needs_intervention,
        )
        self.errors.append(envelope)
        return envelope


@dataclass(slots=True)
class _LocalBackgroundClient:
    submissions: list[Submission]

    def submit_context(
        self,
        *,
        content: str,
        uris: Iterable[str] = (),
        priority: int = _PRIORITY_DEFAULT,
        max_chars: int = 80_000,
    ) -> Submission:
        if len(content) > max_chars:
            original_len = len(content)
            content = (
                content[:max_chars]
                + f"\n\n[Content truncated: original was {original_len:,} chars, "
                f"showing first {max_chars:,}.]"
            )
        submission = Submission(text=content, uris=uris, priority=priority)
        self.submissions.append(submission)
        return submission


@dataclass(slots=True)
class LocalBackgroundContext:
    run_num: int
    run_info: None
    bg: _LocalBackgroundClient
    app_runtime: _LocalRuntimeReporter


class BackgroundApp(Generic[WorkerT, ResultT]):
    AUTH_FAILURE_THRESHOLD: int = 3

    def __init__(self, name: str, *, logger_name: str | None = None) -> None:
        self.name = name
        self.logger = logging.getLogger(logger_name or f"{name}.background")
        self.logger.setLevel(logging.INFO)
        self._worker: WorkerT | None = None
        self._error_reporter = ErrorReporter(logger=self.logger, app_name=name)
        self._consecutive_auth_failures: int = 0

    def build_worker(self) -> WorkerT:
        raise NotImplementedError

    def verify_worker(self, worker: WorkerT) -> tuple[bool, str]:
        verify = getattr(worker, "verify", None)
        if callable(verify):
            return verify()
        return True, f"{self.name} background verified"

    def run_cycle(self, worker: WorkerT) -> ResultT:
        raise NotImplementedError

    def handle_cycle_result(self, ctx: Any, result: ResultT) -> None:
        raise NotImplementedError

    def report_auth_failure(self, ctx: Any, description: str) -> None:
        """Report auth failure with dedup. Only reports after AUTH_FAILURE_THRESHOLD consecutive failures."""
        self._consecutive_auth_failures += 1
        if self._consecutive_auth_failures >= self.AUTH_FAILURE_THRESHOLD:
            self.logger.error("auth failure (count=%d, threshold reached): %s", self._consecutive_auth_failures, description)
            ctx.app_runtime.report_error(
                error_type=2,  # APP_ERROR_AUTH
                error_message=f"{self.name} authentication failure: {description}",
                needs_intervention=True,
            )
        else:
            self.logger.warning("auth failure (count=%d/%d, suppressed): %s", self._consecutive_auth_failures, self.AUTH_FAILURE_THRESHOLD, description)

    def reset_auth_failures(self) -> None:
        if self._consecutive_auth_failures > 0:
            self.logger.info("auth failure streak reset (was %d)", self._consecutive_auth_failures)
        self._consecutive_auth_failures = 0

    def submit_text(
        self,
        ctx: Any,
        *,
        content: str,
        priority: int = _PRIORITY_DEFAULT,
        uris: Iterable[str] = (),
    ) -> Submission | Any:
        return ctx.bg.submit_context(content=content, uris=uris, priority=priority)

    def get_worker(self) -> WorkerT:
        if self._worker is None:
            self._worker = self.build_worker()
        return self._worker

    def reset_for_test(self) -> None:
        self._worker = None

    def verify(self) -> tuple[bool, str]:
        worker = self.get_worker()
        return self.verify_worker(worker)

    def run_once_for_test(self, *, run_num: int = 0) -> LocalBackgroundContext:
        ctx = LocalBackgroundContext(
            run_num=run_num,
            run_info=None,
            bg=_LocalBackgroundClient(submissions=[]),
            app_runtime=_LocalRuntimeReporter(errors=[]),
        )
        self._execute_cycle(ctx)
        return ctx

    def main(self) -> None:
        if "--verify" in sys.argv:
            ok, message = self.verify()
            print(message, flush=True)
            raise SystemExit(0 if ok else 1)

        from app_runtime.background import run_background

        run_background(self._execute_cycle)

    def logger_names(self) -> list[str]:
        return [self.logger.name]

    def _execute_cycle(self, ctx: Any) -> None:
        worker = self.get_worker()
        try:
            result = self.run_cycle(worker)
            self.handle_cycle_result(ctx, result)
        except Exception as exc:
            self._error_reporter.report_background_exception(ctx, exc, phase="background_cycle")


class BackgroundWorkerApp(BackgroundApp[WorkerT, ResultT]):
    pass
