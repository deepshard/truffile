from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HardwarePowerControlRequest(_message.Message):
    __slots__ = ("action",)
    class HardwarePowerControlAction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        CONTROL_ACTION_UNSPECIFIED: _ClassVar[HardwarePowerControlRequest.HardwarePowerControlAction]
        CONTROL_ACTION_REBOOT: _ClassVar[HardwarePowerControlRequest.HardwarePowerControlAction]
        CONTROL_ACTION_SHUTDOWN: _ClassVar[HardwarePowerControlRequest.HardwarePowerControlAction]
    CONTROL_ACTION_UNSPECIFIED: HardwarePowerControlRequest.HardwarePowerControlAction
    CONTROL_ACTION_REBOOT: HardwarePowerControlRequest.HardwarePowerControlAction
    CONTROL_ACTION_SHUTDOWN: HardwarePowerControlRequest.HardwarePowerControlAction
    ACTION_FIELD_NUMBER: _ClassVar[int]
    action: HardwarePowerControlRequest.HardwarePowerControlAction
    def __init__(self, action: _Optional[_Union[HardwarePowerControlRequest.HardwarePowerControlAction, str]] = ...) -> None: ...

class HardwarePowerControlResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
