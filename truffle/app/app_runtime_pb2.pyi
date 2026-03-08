from truffle.app import app_pb2 as _app_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AppRuntimeReportErrorRequest(_message.Message):
    __slots__ = ("app_uuid", "error", "needs_intervention")
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    NEEDS_INTERVENTION_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    error: _app_pb2.AppError
    needs_intervention: bool
    def __init__(self, app_uuid: _Optional[str] = ..., error: _Optional[_Union[_app_pb2.AppError, _Mapping]] = ..., needs_intervention: bool = ...) -> None: ...

class AppRuntimeReportErrorResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
