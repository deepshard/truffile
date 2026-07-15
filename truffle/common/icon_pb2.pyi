from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class Icon(_message.Message):
    __slots__ = ("png_data",)
    PNG_DATA_FIELD_NUMBER: _ClassVar[int]
    png_data: bytes
    def __init__(self, png_data: _Optional[bytes] = ...) -> None: ...
