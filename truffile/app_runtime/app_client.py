from __future__ import annotations

from dataclasses import dataclass

import grpc
from truffle.app.app_pb2 import AppError
from truffle.app.app_runtime_pb2 import (
    AppRuntimeReportErrorRequest,
    AppRuntimeGetAppVarRequest,
    AppRuntimeSetAppVarRequest,
    AppRuntimeDeleteAppVarRequest,
    AppRuntimeListAppVarsRequest,
    AppRuntimeAcquireForegroundMcpRequest,
    AppRuntimeRefreshForegroundMcpRequest,
    AppRuntimeReleaseForegroundMcpRequest,
)
from truffle.app.app_runtime_pb2_grpc import AppRuntimeServiceStub
from enum import IntEnum
from .core import RuntimeConnectionInfo, build_auth_metadata, load_runtime_connection_info


@dataclass(frozen=True, slots=True)
class ForegroundMcpInfo:
    address: str
    port: int
    path: str
    lease_duration_seconds: int

    @property
    def url(self) -> str:
        return f"http://{self.address}:{self.port}{self.path}"

class AppRuntimeErrorType(IntEnum):
    APP_ERROR_INVALID = 0
    APP_ERROR_RUNTIME = 1
    APP_ERROR_AUTH = 2
    APP_ERROR_UNKNOWN = 3

def _app_runtime_error_type_to_pb(error_type: AppRuntimeErrorType | int) -> AppError.ErrorType:
    if isinstance(error_type, AppRuntimeErrorType):
        error_type = int(error_type)
    if error_type == AppRuntimeErrorType.APP_ERROR_RUNTIME:
        return AppError.APP_ERROR_RUNTIME
    elif error_type == AppRuntimeErrorType.APP_ERROR_AUTH:
        return AppError.APP_ERROR_AUTH
    else:
        return AppError.APP_ERROR_UNKNOWN


class AppRuntimeClient:
    def __init__(
        self,
        channel: grpc.Channel,
        *,
        connection: RuntimeConnectionInfo | None = None,
    ) -> None:
        self._connection = connection or load_runtime_connection_info()
        self._stub = AppRuntimeServiceStub(channel)

    def report_error(
        self,
        *,
        error_type: AppRuntimeErrorType | int,
        error_message: str,
        needs_intervention: bool = False,
        app_uuid: str | None = None,
    ):
        req = AppRuntimeReportErrorRequest()
        req.app_uuid = app_uuid or self._connection.app_id
        req.error.error_type = _app_runtime_error_type_to_pb(error_type)
        req.error.error_message = error_message
        req.needs_intervention = needs_intervention
        return self._stub.ReportError(req, metadata=build_auth_metadata(self._connection))

    def report_runtime_error(
        self,
        error_message: str,
        *,
        needs_intervention: bool = False,
        app_uuid: str | None = None,
    ):
        return self.report_error(
            error_type=AppError.APP_ERROR_RUNTIME,
            error_message=error_message,
            needs_intervention=needs_intervention,
            app_uuid=app_uuid,
        )

    def get_app_var(self, key: str) -> str | None:
        req = AppRuntimeGetAppVarRequest()
        req.key = key
        try:
            resp = self._stub.GetAppVar(req, metadata=build_auth_metadata(self._connection))
        except grpc.RpcError as exc:
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise
        return resp.value

    def set_app_var(self, key: str, value: str) -> None:
        req = AppRuntimeSetAppVarRequest()
        req.key = key
        req.value = value
        self._stub.SetAppVar(req, metadata=build_auth_metadata(self._connection))

    def delete_app_var(self, key: str) -> None:
        req = AppRuntimeDeleteAppVarRequest()
        req.key = key
        self._stub.DeleteAppVar(req, metadata=build_auth_metadata(self._connection))

    def list_app_vars(self) -> dict[str, str]:
        req = AppRuntimeListAppVarsRequest()
        resp = self._stub.ListAppVars(req, metadata=build_auth_metadata(self._connection))
        return dict(resp.vars)

    def acquire_foreground_mcp(self, *, lease_duration_seconds: int = 0) -> ForegroundMcpInfo:
        req = AppRuntimeAcquireForegroundMcpRequest()
        req.lease_duration_seconds = lease_duration_seconds
        resp = self._stub.AcquireForegroundMcp(req, metadata=build_auth_metadata(self._connection))
        return ForegroundMcpInfo(
            address=resp.mcp_server.address,
            port=resp.mcp_server.port,
            path=resp.mcp_server.path,
            lease_duration_seconds=resp.lease_duration_seconds,
        )

    def refresh_foreground_mcp(self, *, lease_duration_seconds: int = 0) -> int:
        req = AppRuntimeRefreshForegroundMcpRequest()
        req.lease_duration_seconds = lease_duration_seconds
        resp = self._stub.RefreshForegroundMcp(req, metadata=build_auth_metadata(self._connection))
        return resp.lease_duration_seconds

    def release_foreground_mcp(self) -> None:
        req = AppRuntimeReleaseForegroundMcpRequest()
        self._stub.ReleaseForegroundMcp(req, metadata=build_auth_metadata(self._connection))

async def report_app_error(
    error_message: str,
    *,
    error_type: AppRuntimeErrorType | int = AppRuntimeErrorType.APP_ERROR_RUNTIME,
    needs_intervention: bool = False,
    is_fatal: bool = False
) -> bool:
    try:
        from app_runtime.core import init_channel
        with init_channel() as channel:
            client = AppRuntimeClient(channel)
            client.report_error(
                error_type=error_type,
                error_message=error_message,
                needs_intervention=needs_intervention,
            )
        return True
    except Exception:
        print(f"Failed to report app error: {error_message}")
        print("Exception details:")
        import traceback
        traceback.print_exc()
        # Don't raise exceptions from error reporting to avoid potential infinite loops.
        pass
    return False
