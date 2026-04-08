from __future__ import annotations




from truffile.app_runtime import BackgroundWorkerApp

from reddit_bg_worker import BgRunResult, RedditBackgroundWorker


class RedditBackgroundApp(BackgroundWorkerApp[RedditBackgroundWorker, BgRunResult]):
    def __init__(self) -> None:
        super().__init__("reddit", logger_name="reddit.background")

    def build_worker(self) -> RedditBackgroundWorker:
        return RedditBackgroundWorker()

    def verify_worker(self, worker: RedditBackgroundWorker) -> tuple[bool, str]:
        return worker.verify()

    def run_cycle(self, worker: RedditBackgroundWorker) -> BgRunResult:
        return worker.run_cycle()

    def handle_cycle_result(self, ctx: object, result: BgRunResult) -> None:
        if result.error:
            self.logger.error("Reddit background cycle failed", extra={"error": result.error})
            if result.error == "auth_failure":
                self.report_auth_failure(ctx, result.error)
            return
        self.reset_auth_failures()
        if not result.submissions:
            self.logger.info("Reddit background cycle produced no new posts")
            return
        for submission in result.submissions:
            self.submit_text(
                ctx,
                content=submission.text,
                uris=submission.uris,
                priority=submission.priority,
            )


app = RedditBackgroundApp()


if __name__ == "__main__":
    app.main()
