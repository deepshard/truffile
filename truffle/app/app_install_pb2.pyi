from truffle.os import installer_pb2 as _installer_pb2
from truffle.app import app_build_pb2 as _app_build_pb2
from truffle.app import background_pb2 as _background_pb2
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
    __slots__ = ("process_config", "bg_rt_policy")
    PROCESS_CONFIG_FIELD_NUMBER: _ClassVar[int]
    BG_RT_POLICY_FIELD_NUMBER: _ClassVar[int]
    process_config: _app_build_pb2.ProcessConfig
    bg_rt_policy: _background_pb2.BackgroundAppRuntimePolicy
    def __init__(self, process_config: _Optional[_Union[_app_build_pb2.ProcessConfig, _Mapping]] = ..., bg_rt_policy: _Optional[_Union[_background_pb2.BackgroundAppRuntimePolicy, _Mapping]] = ...) -> None: ...
