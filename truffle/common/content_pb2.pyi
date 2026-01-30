from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class MediaSource(_message.Message):
    __slots__ = ("uri",)
    URI_FIELD_NUMBER: _ClassVar[int]
    uri: str
    def __init__(self, uri: _Optional[str] = ...) -> None: ...

class WebComponent(_message.Message):
    __slots__ = ("uri", "width", "height")
    URI_FIELD_NUMBER: _ClassVar[int]
    WIDTH_FIELD_NUMBER: _ClassVar[int]
    HEIGHT_FIELD_NUMBER: _ClassVar[int]
    uri: str
    width: int
    height: int
    def __init__(self, uri: _Optional[str] = ..., width: _Optional[int] = ..., height: _Optional[int] = ...) -> None: ...
