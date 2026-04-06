from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any


class AppRuntimeFailure(RuntimeError):
    pass


class AppAuthError(AppRuntimeFailure):
    pass


@dataclass(frozen=True, slots=True)
class ErrorEnvelope:
    error_type: int
    error_message: str
    needs_intervention: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "needs_intervention": self.needs_intervention,
        }


def _classify_error(exc: BaseException) -> tuple[int, bool, str]:
    if isinstance(exc, AppAuthError):
        return 2, True, "auth"
    return 1, False, "runtime"


class ErrorReporter:
    def __init__(self, *, logger: logging.Logger, app_name: str) -> None:
        self._logger = logger
        self._app_name = app_name

    async def report_foreground_exception(self, exc: BaseException, *, tool_name: str) -> None:
        error_type, needs_intervention, category = _classify_error(exc)
        message = f"{self._app_name} foreground tool '{tool_name}' failed ({category}): {exc}"
        self._logger.exception(
            "Foreground tool failed",
            extra={
                "app_name": self._app_name,
                "tool_name": tool_name,
                "error_category": category,
            },
        )
        if category != "auth":
            return
        try:
            from app_runtime import report_app_error

            await report_app_error(
                message,
                error_type=error_type,
                needs_intervention=needs_intervention,
            )
        except Exception:
            self._logger.exception("Failed reporting foreground tool error")

    def report_background_exception(self, ctx: Any, exc: BaseException, *, phase: str) -> ErrorEnvelope:
        error_type, needs_intervention, category = _classify_error(exc)
        message = f"{self._app_name} {phase} failed ({category}): {exc}"
        self._logger.exception(
            "Background phase failed",
            extra={
                "app_name": self._app_name,
                "phase": phase,
                "error_category": category,
            },
        )

        envelope = ErrorEnvelope(
            error_type=error_type,
            error_message=message,
            needs_intervention=needs_intervention,
        )

        reporter = getattr(ctx, "app_runtime", None)
        if reporter is not None:
            try:
                reporter.report_error(
                    error_type=error_type,
                    error_message=message,
                    needs_intervention=needs_intervention,
                )
            except Exception:
                self._logger.exception("Failed reporting background runtime error")
        return envelope
