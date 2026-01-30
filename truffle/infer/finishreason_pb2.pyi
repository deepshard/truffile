from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from typing import ClassVar as _ClassVar

DESCRIPTOR: _descriptor.FileDescriptor

class FinishReason(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    FINISH_UNSPECIFIED: _ClassVar[FinishReason]
    FINISH_STOP: _ClassVar[FinishReason]
    FINISH_LENGTH: _ClassVar[FinishReason]
    FINISH_TOOLCALLS: _ClassVar[FinishReason]
    FINISH_ERROR: _ClassVar[FinishReason]
    FINISH_ABORT: _ClassVar[FinishReason]
    FINISH_UNKNOWN: _ClassVar[FinishReason]
    FINISH_GOAWAY: _ClassVar[FinishReason]
FINISH_UNSPECIFIED: FinishReason
FINISH_STOP: FinishReason
FINISH_LENGTH: FinishReason
FINISH_TOOLCALLS: FinishReason
FINISH_ERROR: FinishReason
FINISH_ABORT: FinishReason
FINISH_UNKNOWN: FinishReason
FINISH_GOAWAY: FinishReason
