from __future__ import annotations

import atexit



from truffile.app_runtime import BackgroundWorkerApp
from truffle.app.background_pb2 import BackgroundContext

from bg_worker import CycleResult, GitHubBackgroundWorker, is_hard_auth_failure
from config import AUTH_FAILURE_REPORT_THRESHOLD
import os

_PRIORITY_LOW = getattr(BackgroundContext, "PRIORITY_LOW", 0)


class _StubGitHubBackgroundWorker:
    def verify(self) -> tuple[bool, str]:
        return True, "GitHub background verify OK (user=@octocat)"

    def run_cycle(self) -> CycleResult:
        return CycleResult(
            summary="GitHub activity digest (2026-03-23T00:00:00+00:00) for @octocat",
            uris=["https://github.com/truffle-ai/pyfw-codex/pull/1"],
            priority=1,
            changed=True,
        )


class GitHubBackgroundApp(BackgroundWorkerApp[GitHubBackgroundWorker, CycleResult]):
    def __init__(self) -> None:
        super().__init__("github", logger_name="github.background")
        self._consecutive_auth_failures = 0

    def build_worker(self) -> GitHubBackgroundWorker:
        if os.getenv("APP_STORE_USE_TEST_STUBS") == "1":
            return _StubGitHubBackgroundWorker()  # type: ignore[return-value]
        return GitHubBackgroundWorker()

    def verify_worker(self, worker: GitHubBackgroundWorker) -> tuple[bool, str]:
        return worker.verify()

    def reset_for_test(self) -> None:
        worker = getattr(self, "_worker", None)
        close = getattr(worker, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                self.logger.exception("Failed to close GitHub background worker during reset")
        super().reset_for_test()
        self._consecutive_auth_failures = 0

    def cleanup(self) -> None:
        self.reset_for_test()

    def run_cycle(self, worker: GitHubBackgroundWorker) -> CycleResult:
        close = getattr(worker, "close", None)
        if callable(close):
            close()
        return worker.run_cycle()

    def handle_cycle_result(self, ctx: object, result: CycleResult) -> None:
        if result.auth_error:
            self._consecutive_auth_failures += 1
            hard_failure = is_hard_auth_failure(result.auth_error)
            self.logger.error(
                "GitHub background auth check failed (%d consecutive): %s",
                self._consecutive_auth_failures,
                result.auth_error,
            )
            if not hard_failure and self._consecutive_auth_failures < AUTH_FAILURE_REPORT_THRESHOLD:
                return
            reporter = getattr(ctx, "app_runtime", None)
            if reporter is not None:
                reporter.report_error(
                    error_type=2,
                    error_message=f"GitHub authentication failure: {result.auth_error}",
                    needs_intervention=True,
                )
            return

        self._consecutive_auth_failures = 0

        if result.error:
            self.logger.error("GitHub background cycle failed: %s", result.error)
            return
        if not result.changed or not result.summary:
            self.logger.info("GitHub background cycle unchanged; skipping submit_context")
            return
        self.submit_text(ctx, content=result.summary, uris=result.uris, priority=result.priority or _PRIORITY_LOW)


app = GitHubBackgroundApp()


atexit.register(app.cleanup)


if __name__ == "__main__":
    app.main()
