from __future__ import annotations

import grpc
from truffle.app.app_pb2 import AppError
from truffle.app.app_runtime_pb2 import AppRuntimeReportErrorRequest
from truffle.app.app_runtime_pb2_grpc import AppRuntimeServiceStub
from enum import IntEnum
from .core import RuntimeConnectionInfo, build_auth_metadata, load_runtime_connection_info

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
