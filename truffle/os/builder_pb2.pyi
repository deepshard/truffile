from truffle.app import background_pb2 as _background_pb2
from truffle.app import foreground_pb2 as _foreground_pb2
from truffle.app import app_build_pb2 as _app_build_pb2
from truffle.app import app_pb2 as _app_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class StartBuildSessionRequest(_message.Message):
    __slots__ = ("app_uuid",)
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    def __init__(self, app_uuid: _Optional[str] = ...) -> None: ...

class StartBuildSessionResponse(_message.Message):
    __slots__ = ("access_path", "app_uuid")
    ACCESS_PATH_FIELD_NUMBER: _ClassVar[int]
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    access_path: str
    app_uuid: str
    def __init__(self, access_path: _Optional[str] = ..., app_uuid: _Optional[str] = ...) -> None: ...

class FinishBuildSessionRequest(_message.Message):
    __slots__ = ("app_uuid", "discard", "metadata", "foreground", "background")
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    DISCARD_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    FOREGROUND_FIELD_NUMBER: _ClassVar[int]
    BACKGROUND_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    discard: bool
    metadata: _app_pb2.AppMetadata
    foreground: _foreground_pb2.ForegroundAppBuildInfo
    background: _background_pb2.BackgroundAppBuildInfo
    def __init__(self, app_uuid: _Optional[str] = ..., discard: bool = ..., metadata: _Optional[_Union[_app_pb2.AppMetadata, _Mapping]] = ..., foreground: _Optional[_Union[_foreground_pb2.ForegroundAppBuildInfo, _Mapping]] = ..., background: _Optional[_Union[_background_pb2.BackgroundAppBuildInfo, _Mapping]] = ...) -> None: ...

class BuildSessionError(_message.Message):
    __slots__ = ("error", "details")
    ERROR_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    error: str
    details: str
    def __init__(self, error: _Optional[str] = ..., details: _Optional[str] = ...) -> None: ...

class FinishBuildSessionResponse(_message.Message):
    __slots__ = ("error",)
    ERROR_FIELD_NUMBER: _ClassVar[int]
    error: BuildSessionError
    def __init__(self, error: _Optional[_Union[BuildSessionError, _Mapping]] = ...) -> None: ...
