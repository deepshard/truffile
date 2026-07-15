import datetime

from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SystemMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MODE_INVALID: _ClassVar[SystemMode]
    MODE_NORMAL: _ClassVar[SystemMode]
    MODE_DREAM: _ClassVar[SystemMode]
MODE_INVALID: SystemMode
MODE_NORMAL: SystemMode
MODE_DREAM: SystemMode

class RequestSystemModeSetRequest(_message.Message):
    __slots__ = ("mode",)
    MODE_FIELD_NUMBER: _ClassVar[int]
    mode: SystemMode
    def __init__(self, mode: _Optional[_Union[SystemMode, str]] = ...) -> None: ...

class RequestSystemModeSetResponse(_message.Message):
    __slots__ = ("mode",)
    MODE_FIELD_NUMBER: _ClassVar[int]
    mode: SystemMode
    def __init__(self, mode: _Optional[_Union[SystemMode, str]] = ...) -> None: ...

class GetSystemModeRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetSystemModeResponse(_message.Message):
    __slots__ = ("mode",)
    MODE_FIELD_NUMBER: _ClassVar[int]
    mode: SystemMode
    def __init__(self, mode: _Optional[_Union[SystemMode, str]] = ...) -> None: ...

class SystemModeChangeNotification(_message.Message):
    __slots__ = ("new_mode", "eta")
    NEW_MODE_FIELD_NUMBER: _ClassVar[int]
    ETA_FIELD_NUMBER: _ClassVar[int]
    new_mode: SystemMode
    eta: _duration_pb2.Duration
    def __init__(self, new_mode: _Optional[_Union[SystemMode, str]] = ..., eta: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ...) -> None: ...
