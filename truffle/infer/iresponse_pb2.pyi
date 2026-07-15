from truffle.infer import usage_pb2 as _usage_pb2
from truffle.infer import finishreason_pb2 as _finishreason_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class IResponse(_message.Message):
    __slots__ = ("id", "content", "usage", "finish_reason")
    ID_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    USAGE_FIELD_NUMBER: _ClassVar[int]
    FINISH_REASON_FIELD_NUMBER: _ClassVar[int]
    id: str
    content: str
    usage: _usage_pb2.Usage
    finish_reason: _finishreason_pb2.FinishReason
    def __init__(self, id: _Optional[str] = ..., content: _Optional[str] = ..., usage: _Optional[_Union[_usage_pb2.Usage, _Mapping]] = ..., finish_reason: _Optional[_Union[_finishreason_pb2.FinishReason, str]] = ...) -> None: ...

class BatchIResponse(_message.Message):
    __slots__ = ("responses",)
    RESPONSES_FIELD_NUMBER: _ClassVar[int]
    responses: _containers.RepeatedCompositeFieldContainer[IResponse]
    def __init__(self, responses: _Optional[_Iterable[_Union[IResponse, _Mapping]]] = ...) -> None: ...
