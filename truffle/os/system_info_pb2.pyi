from google.protobuf import timestamp_pb2 as _timestamp_pb2
from truffle.os import hardware_info_pb2 as _hardware_info_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union
from truffle.os.hardware_info_pb2 import HardwareInfo as HardwareInfo

DESCRIPTOR: _descriptor.FileDescriptor

class FirmwareVersion(_message.Message):
    __slots__ = ("version",)
    VERSION_FIELD_NUMBER: _ClassVar[int]
    version: str
    def __init__(self, version: _Optional[str] = ...) -> None: ...

class SystemInfo(_message.Message):
    __slots__ = ("system_type", "firmware_version", "hardware_info")
    class TruffleType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        TRUFFLE_TYPE_INVALID: _ClassVar[SystemInfo.TruffleType]
        TRUFFLE_TYPE_HARDWARE: _ClassVar[SystemInfo.TruffleType]
    TRUFFLE_TYPE_INVALID: SystemInfo.TruffleType
    TRUFFLE_TYPE_HARDWARE: SystemInfo.TruffleType
    SYSTEM_TYPE_FIELD_NUMBER: _ClassVar[int]
    FIRMWARE_VERSION_FIELD_NUMBER: _ClassVar[int]
    HARDWARE_INFO_FIELD_NUMBER: _ClassVar[int]
    system_type: SystemInfo.TruffleType
    firmware_version: FirmwareVersion
    hardware_info: _hardware_info_pb2.HardwareInfo
    def __init__(self, system_type: _Optional[_Union[SystemInfo.TruffleType, str]] = ..., firmware_version: _Optional[_Union[FirmwareVersion, _Mapping]] = ..., hardware_info: _Optional[_Union[_hardware_info_pb2.HardwareInfo, _Mapping]] = ...) -> None: ...

class SystemCheckForUpdateRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SystemCheckForUpdateResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SystemGetIDRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SystemGetIDResponse(_message.Message):
    __slots__ = ("truffle_id", "serial_number")
    TRUFFLE_ID_FIELD_NUMBER: _ClassVar[int]
    SERIAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    truffle_id: str
    serial_number: str
    def __init__(self, truffle_id: _Optional[str] = ..., serial_number: _Optional[str] = ...) -> None: ...
