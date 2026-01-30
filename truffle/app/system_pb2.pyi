from truffle.app import background_pb2 as _background_pb2
from truffle.app import app_build_pb2 as _app_build_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SystemApp(_message.Message):
    __slots__ = ("key", "source_dir", "process", "no_ckpt", "schedule_policy")
    KEY_FIELD_NUMBER: _ClassVar[int]
    SOURCE_DIR_FIELD_NUMBER: _ClassVar[int]
    PROCESS_FIELD_NUMBER: _ClassVar[int]
    NO_CKPT_FIELD_NUMBER: _ClassVar[int]
    SCHEDULE_POLICY_FIELD_NUMBER: _ClassVar[int]
    key: str
    source_dir: str
    process: _app_build_pb2.ProcessConfig
    no_ckpt: bool
    schedule_policy: _background_pb2.BackgroundAppRuntimePolicy
    def __init__(self, key: _Optional[str] = ..., source_dir: _Optional[str] = ..., process: _Optional[_Union[_app_build_pb2.ProcessConfig, _Mapping]] = ..., no_ckpt: bool = ..., schedule_policy: _Optional[_Union[_background_pb2.BackgroundAppRuntimePolicy, _Mapping]] = ...) -> None: ...
