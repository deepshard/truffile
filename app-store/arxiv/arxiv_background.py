from __future__ import annotations

import os

from truffile.app_runtime import BackgroundWorkerApp
from truffle.app.background_pb2 import BackgroundContext

from arxiv_bg_worker import ArxivBackgroundWorker, BgRunResult

_PRIORITY_DEFAULT = getattr(
    BackgroundContext,
    "PRIORITY_DEFAULT",
    getattr(BackgroundContext, "PRIORITY_HIGH", 1),
)


class ArxivBackgroundApp(BackgroundWorkerApp[ArxivBackgroundWorker, BgRunResult]):
    def __init__(self) -> None:
        super().__init__("arxiv", logger_name="arxiv.background")

    def build_worker(self) -> ArxivBackgroundWorker:
        interests = str(os.getenv("ARXIV_RESEARCH_INTERESTS", "")).strip()
        return ArxivBackgroundWorker(interests_raw=interests)

    def verify_worker(self, worker: ArxivBackgroundWorker) -> tuple[bool, str]:
        return worker.verify()

    def run_cycle(self, worker: ArxivBackgroundWorker) -> BgRunResult:
        return worker.run_cycle()

    def handle_cycle_result(self, ctx: object, result: BgRunResult) -> None:
        if result.error:
            self.logger.error("ArXiv background cycle failed", extra={"error": result.error})
            return
        if not result.content:
            self.logger.info("ArXiv background cycle produced no new recommendations")
            return
        self.submit_text(
            ctx,
            content=result.content,
            priority=_PRIORITY_DEFAULT,
        )


app = ArxivBackgroundApp()


if __name__ == "__main__":
    app.main()
