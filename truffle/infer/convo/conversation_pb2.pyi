from truffle.infer.convo import msg_pb2 as _msg_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union
from truffle.infer.convo.msg_pb2 import Message as Message

DESCRIPTOR: _descriptor.FileDescriptor

class Conversation(_message.Message):
    __slots__ = ("messages", "model_uuid")
    MESSAGES_FIELD_NUMBER: _ClassVar[int]
    MODEL_UUID_FIELD_NUMBER: _ClassVar[int]
    messages: _containers.RepeatedCompositeFieldContainer[_msg_pb2.Message]
    model_uuid: str
    def __init__(self, messages: _Optional[_Iterable[_Union[_msg_pb2.Message, _Mapping]]] = ..., model_uuid: _Optional[str] = ...) -> None: ...

class BuiltContext(_message.Message):
    __slots__ = ("context", "model_uuid")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    MODEL_UUID_FIELD_NUMBER: _ClassVar[int]
    context: str
    model_uuid: str
    def __init__(self, context: _Optional[str] = ..., model_uuid: _Optional[str] = ...) -> None: ...
