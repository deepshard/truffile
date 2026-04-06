from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Callable

from truffle.app.background_pb2 import BackgroundAppOnRunResponse

from ..app_client import AppRuntimeClient
from ..core import close_channel, init_channel
from .client import BackgroundAppClient

logger = logging.getLogger(__name__)

BackgroundRunFunc = Callable[["BackgroundRunContext"], None]


@dataclass(slots=True)
class BackgroundRunContext:
    run_num: int
    run_info: BackgroundAppOnRunResponse | None
    bg: BackgroundAppClient
    app_runtime: AppRuntimeClient


def run_background(
    func: BackgroundRunFunc,
    *,
    connection_timeout_seconds: float = 15.0,
    wait_interval_seconds: float = 0.5,
) -> None:
    run_num = 0
    while True:
        logger.debug("starting background app run %s", run_num)
        channel = init_channel(timeout_seconds=connection_timeout_seconds)
        bg_client = BackgroundAppClient(channel)
        app_runtime_client = AppRuntimeClient(channel)
        ctx = BackgroundRunContext(
            run_num=run_num,
            run_info=None,
            bg=bg_client,
            app_runtime=app_runtime_client,
        )
        try:
            ctx.run_info = bg_client.on_run()
            func(ctx)
        except Exception as e:
            logger.exception("background app user function failed in run %s", run_num)
            try:
                app_runtime_client.report_runtime_error(str(e), needs_intervention=False)
            except Exception:
                logger.exception("failed to report runtime error")
        finally:
            time.sleep(0.250)
            wait_until = bg_client.yield_run()
            close_channel(channel)

        while datetime.now(timezone.utc) < wait_until:
            time.sleep(wait_interval_seconds)
        run_num += 1
