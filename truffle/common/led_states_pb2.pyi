from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class LedState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    LED_STATE_INVALID: _ClassVar[LedState]
    LED_STATE_DISABLED: _ClassVar[LedState]
    LED_STATE_OFF: _ClassVar[LedState]
    LED_STATE_STARTUP: _ClassVar[LedState]
    LED_STATE_READY_TO_CONNECT: _ClassVar[LedState]
    LED_STATE_CONNECTING: _ClassVar[LedState]
    LED_STATE_CONNECTED: _ClassVar[LedState]
    LED_STATE_ERROR: _ClassVar[LedState]
    LED_STATE_REASONING: _ClassVar[LedState]
    LED_STATE_IDLE: _ClassVar[LedState]
    LED_STATE_TYPING: _ClassVar[LedState]
    LED_STATE_RESPOND_TO_USER: _ClassVar[LedState]
    LED_STATE_ONBOARD: _ClassVar[LedState]
    LED_STATE_ONCE_ACTION: _ClassVar[LedState]
    LED_STATE_ONCE_FLAIR: _ClassVar[LedState]
LED_STATE_INVALID: LedState
LED_STATE_DISABLED: LedState
LED_STATE_OFF: LedState
LED_STATE_STARTUP: LedState
LED_STATE_READY_TO_CONNECT: LedState
LED_STATE_CONNECTING: LedState
LED_STATE_CONNECTED: LedState
LED_STATE_ERROR: LedState
LED_STATE_REASONING: LedState
LED_STATE_IDLE: LedState
LED_STATE_TYPING: LedState
LED_STATE_RESPOND_TO_USER: LedState
LED_STATE_ONBOARD: LedState
LED_STATE_ONCE_ACTION: LedState
LED_STATE_ONCE_FLAIR: LedState

class LedStatus(_message.Message):
    __slots__ = ("state", "color")
    STATE_FIELD_NUMBER: _ClassVar[int]
    COLOR_FIELD_NUMBER: _ClassVar[int]
    state: LedState
    color: int
    def __init__(self, state: _Optional[_Union[LedState, str]] = ..., color: _Optional[int] = ...) -> None: ...
