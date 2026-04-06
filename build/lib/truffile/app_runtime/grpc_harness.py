from __future__ import annotations

import os
from concurrent import futures
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import grpc


_PROTO_IMPORT_ERROR = (
    "Protobuf stubs not found. Run the pyfw proto generation step before using grpc_harness."
)


def _import_protos() -> tuple[Any, ...]:
    try:
        from truffle.app import app_runtime_pb2, app_runtime_pb2_grpc
        from truffle.app import background_pb2, background_pb2_grpc
    except ImportError as exc:
        raise ImportError(_PROTO_IMPORT_ERROR) from exc
    return background_pb2, background_pb2_grpc, app_runtime_pb2, app_runtime_pb2_grpc



@dataclass(slots=True)
class RecordedSubmission:
    content: str = ""
    uris: list[str] = field(default_factory=list)
    priority: int = 0


@dataclass(slots=True)
class RecordedRuntimeError:
    app_uuid: str = ""
    error_type: int = 0
    error_message: str = ""
    needs_intervention: bool = False


class FakeBackgroundAppServicer:
    def __init__(self) -> None:
        self.on_run_calls = 0
        self.yield_calls = 0
        self.submissions: list[RecordedSubmission] = []
        self._pb2: Any = None

    def _ensure_pb2(self) -> Any:
        if self._pb2 is None:
            self._pb2 = _import_protos()[0]
        return self._pb2

    def OnRun(self, request: Any, context: Any) -> Any:
        pb2 = self._ensure_pb2()
        self.on_run_calls += 1
        return pb2.BackgroundAppOnRunResponse()

    def Yield(self, request: Any, context: Any) -> Any:
        pb2 = self._ensure_pb2()
        self.yield_calls += 1
        resp = pb2.BackgroundAppYieldResponse()
        resp.next_scheduled_run_time.FromDatetime(datetime.now(timezone.utc))
        return resp

    def Submit(self, request: Any, context: Any) -> Any:
        pb2 = self._ensure_pb2()
        self.submissions.append(
            RecordedSubmission(
                content=request.content.content,
                uris=list(request.content.uris),
                priority=int(request.content.priority),
            )
        )
        return pb2.BackgroundAppSubmitContextResponse()


class FakeAppRuntimeServicer:
    def __init__(self) -> None:
        self.errors: list[RecordedRuntimeError] = []
        self.app_vars: dict[str, str] = {}
        self._pb2: Any = None

    def _ensure_pb2(self) -> Any:
        if self._pb2 is None:
            self._pb2 = _import_protos()[2]
        return self._pb2

    def ReportError(self, request: Any, context: Any) -> Any:
        pb2 = self._ensure_pb2()
        self.errors.append(
            RecordedRuntimeError(
                app_uuid=request.app_uuid,
                error_type=int(request.error.error_type),
                error_message=request.error.error_message,
                needs_intervention=bool(request.needs_intervention),
            )
        )
        return pb2.AppRuntimeReportErrorResponse()

    def GetAppVar(self, request: Any, context: Any) -> Any:
        pb2 = self._ensure_pb2()
        value = self.app_vars.get(request.key, "")
        if not value:
            context.set_code(grpc.StatusCode.NOT_FOUND)
        return pb2.AppRuntimeGetAppVarResponse(value=value)

    def SetAppVar(self, request: Any, context: Any) -> Any:
        pb2 = self._ensure_pb2()
        self.app_vars[request.key] = request.value
        return pb2.AppRuntimeSetAppVarResponse()

    def DeleteAppVar(self, request: Any, context: Any) -> Any:
        pb2 = self._ensure_pb2()
        self.app_vars.pop(request.key, None)
        return pb2.AppRuntimeDeleteAppVarResponse()

    def ListAppVars(self, request: Any, context: Any) -> Any:
        pb2 = self._ensure_pb2()
        resp = pb2.AppRuntimeListAppVarsResponse()
        for k, v in self.app_vars.items():
            resp.vars[k] = v
        return resp


class InProcessGrpcServer:
    def __init__(
        self,
        *,
        app_id: str = "test-app-id",
        session_token: str = "test-session-token",
        max_workers: int = 4,
    ) -> None:
        self.app_id = app_id
        self.session_token = session_token
        self._max_workers = max_workers
        self._server: grpc.Server | None = None
        self._port = 0
        self._saved_env: dict[str, str | None] = {}
        self.bg_servicer = FakeBackgroundAppServicer()
        self.runtime_servicer = FakeAppRuntimeServicer()

    @property
    def address(self) -> str:
        return f"127.0.0.1:{self._port}"

    def __enter__(self) -> InProcessGrpcServer:
        background_pb2, background_pb2_grpc, app_runtime_pb2, app_runtime_pb2_grpc = _import_protos()
        del background_pb2, app_runtime_pb2
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=self._max_workers))
        background_pb2_grpc.add_BackgroundAppServiceServicer_to_server(self.bg_servicer, self._server)
        app_runtime_pb2_grpc.add_AppRuntimeServiceServicer_to_server(self.runtime_servicer, self._server)
        self._port = self._server.add_insecure_port("127.0.0.1:0")
        self._server.start()

        env_overrides = {
            "APP_ID": self.app_id,
            "APP_SESSION_TOKEN": self.session_token,
            "GRPC_ADDRESS": self.address,
        }
        for key, value in env_overrides.items():
            self._saved_env[key] = os.environ.get(key)
            os.environ[key] = value
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._server is not None:
            self._server.stop(grace=0)
            self._server = None
        for key, original in self._saved_env.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original
        self._saved_env.clear()

    def run_background_once(self, func: Any, *, connection_timeout_seconds: float = 5.0) -> None:
        from app_runtime.app_client import AppRuntimeClient
        from app_runtime.background.client import BackgroundAppClient
        from app_runtime.background.runtime import BackgroundRunContext
        from app_runtime.core import close_channel, init_channel

        channel = init_channel(timeout_seconds=connection_timeout_seconds)
        try:
            bg_client = BackgroundAppClient(channel)
            runtime_client = AppRuntimeClient(channel)
            run_info = bg_client.on_run()
            ctx = BackgroundRunContext(
                run_num=0,
                run_info=run_info,
                bg=bg_client,
                app_runtime=runtime_client,
            )
            func(ctx)
            bg_client.yield_run()
        finally:
            close_channel(channel)
