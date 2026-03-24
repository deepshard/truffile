from __future__ import annotations

import atexit
import logging
import os
import sys

from app_runtime.background import BackgroundRunContext, run_background
from truffle.app.background_pb2 import BackgroundContext

from arxiv_bg_worker import ArxivBackgroundWorker

logger = logging.getLogger("arxiv.background")
logger.setLevel(logging.INFO)

_worker: ArxivBackgroundWorker | None = None
_PRIORITY_DEFAULT = getattr(
    BackgroundContext,
    "PRIORITY_DEFAULT",
    getattr(BackgroundContext, "PRIORITY_HIGH", 1),
)


def _is_verify_mode() -> bool:
    return bool(sys.argv and len(sys.argv) > 1 and "verify" in sys.argv[1].lower())


def _ensure_worker() -> ArxivBackgroundWorker:
    global _worker
    if _worker is None:
        interests = str(os.getenv("ARXIV_RESEARCH_INTERESTS", "")).strip()
        _worker = ArxivBackgroundWorker(interests_raw=interests)
    return _worker


def _submit(ctx: BackgroundRunContext, content: str) -> None:
    ctx.bg.submit_context(
        content=content,
        uris=[],
        priority=_PRIORITY_DEFAULT,
    )


def arxiv_ambient(ctx: BackgroundRunContext) -> None:
    worker = _ensure_worker()
    result = worker.run_cycle()

    if result.error:
        logger.error("ArXiv background cycle failed", extra={"error": result.error})
        return
    if not result.content:
        logger.info("ArXiv background cycle produced no new recommendations")
        return

    _submit(ctx, result.content)


def verify() -> int:
    worker = _ensure_worker()
    ok, message = worker.verify()
    if ok:
        logger.info(message)
        return 0
    logger.error(message)
    return 1


def _cleanup() -> None:
    global _worker
    _worker = None


if __name__ == "__main__":
    atexit.register(_cleanup)
    if _is_verify_mode():
        sys.exit(verify())
    run_background(arxiv_ambient)
