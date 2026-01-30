from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class TokenizeRequest(_message.Message):
    __slots__ = ("texts", "model_uuid")
    TEXTS_FIELD_NUMBER: _ClassVar[int]
    MODEL_UUID_FIELD_NUMBER: _ClassVar[int]
    texts: _containers.RepeatedScalarFieldContainer[str]
    model_uuid: str
    def __init__(self, texts: _Optional[_Iterable[str]] = ..., model_uuid: _Optional[str] = ...) -> None: ...

class TokenizeResponse(_message.Message):
    __slots__ = ("lengths",)
    LENGTHS_FIELD_NUMBER: _ClassVar[int]
    lengths: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, lengths: _Optional[_Iterable[int]] = ...) -> None: ...
