from truffle.os import installer_pb2 as _installer_pb2
from truffle.app import app_pb2 as _app_pb2
from truffle.app import app_build_pb2 as _app_build_pb2
from truffle.app import background_pb2 as _background_pb2
from truffle.app import foreground_pb2 as _foreground_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetFinalInstallInfoRequest(_message.Message):
    __slots__ = ("app_uuid",)
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    def __init__(self, app_uuid: _Optional[str] = ...) -> None: ...

class GetFinalInstallInfoResponse(_message.Message):
    __slots__ = ("bg_build_info", "fg_build_info")
    BG_BUILD_INFO_FIELD_NUMBER: _ClassVar[int]
    FG_BUILD_INFO_FIELD_NUMBER: _ClassVar[int]
    bg_build_info: _background_pb2.BackgroundAppBuildInfo
    fg_build_info: _foreground_pb2.ForegroundAppBuildInfo
    def __init__(self, bg_build_info: _Optional[_Union[_background_pb2.BackgroundAppBuildInfo, _Mapping]] = ..., fg_build_info: _Optional[_Union[_foreground_pb2.ForegroundAppBuildInfo, _Mapping]] = ...) -> None: ...
