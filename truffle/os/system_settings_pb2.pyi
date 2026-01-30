from truffle.os import hardware_settings_pb2 as _hardware_settings_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union
from truffle.os.hardware_settings_pb2 import HardwareSettings as HardwareSettings

DESCRIPTOR: _descriptor.FileDescriptor

class SystemSettings(_message.Message):
    __slots__ = ("hardware_settings", "task_settings")
    HARDWARE_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    TASK_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    hardware_settings: _hardware_settings_pb2.HardwareSettings
    task_settings: TaskSettings
    def __init__(self, hardware_settings: _Optional[_Union[_hardware_settings_pb2.HardwareSettings, _Mapping]] = ..., task_settings: _Optional[_Union[TaskSettings, _Mapping]] = ...) -> None: ...

class TaskSettings(_message.Message):
    __slots__ = ("default_model_uuid",)
    DEFAULT_MODEL_UUID_FIELD_NUMBER: _ClassVar[int]
    default_model_uuid: str
    def __init__(self, default_model_uuid: _Optional[str] = ...) -> None: ...
