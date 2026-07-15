from truffle.infer import gencfg_pb2 as _gencfg_pb2
from truffle.infer.convo import conversation_pb2 as _conversation_pb2
from truffle.infer.convo import msg_pb2 as _msg_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RequestPriority(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    REQUEST_PRIORITY_UNSPECIFIED: _ClassVar[RequestPriority]
    REQUEST_PRIORITY_LOW: _ClassVar[RequestPriority]
    REQUEST_PRIORITY_NORMAL: _ClassVar[RequestPriority]
    REQUEST_PRIORITY_REALTIME: _ClassVar[RequestPriority]
REQUEST_PRIORITY_UNSPECIFIED: RequestPriority
REQUEST_PRIORITY_LOW: RequestPriority
REQUEST_PRIORITY_NORMAL: RequestPriority
REQUEST_PRIORITY_REALTIME: RequestPriority

class IRequest(_message.Message):
    __slots__ = ("id", "raw", "convo", "cfg", "model_uuid", "priority")
    ID_FIELD_NUMBER: _ClassVar[int]
    RAW_FIELD_NUMBER: _ClassVar[int]
    CONVO_FIELD_NUMBER: _ClassVar[int]
    CFG_FIELD_NUMBER: _ClassVar[int]
    MODEL_UUID_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    id: str
    raw: str
    convo: _conversation_pb2.Conversation
    cfg: _gencfg_pb2.GenerationConfig
    model_uuid: str
    priority: RequestPriority
    def __init__(self, id: _Optional[str] = ..., raw: _Optional[str] = ..., convo: _Optional[_Union[_conversation_pb2.Conversation, _Mapping]] = ..., cfg: _Optional[_Union[_gencfg_pb2.GenerationConfig, _Mapping]] = ..., model_uuid: _Optional[str] = ..., priority: _Optional[_Union[RequestPriority, str]] = ...) -> None: ...

class BatchIRequest(_message.Message):
    __slots__ = ("requests",)
    REQUESTS_FIELD_NUMBER: _ClassVar[int]
    requests: _containers.RepeatedCompositeFieldContainer[IRequest]
    def __init__(self, requests: _Optional[_Iterable[_Union[IRequest, _Mapping]]] = ...) -> None: ...
