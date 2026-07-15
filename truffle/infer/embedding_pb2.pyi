from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Embeddable(_message.Message):
    __slots__ = ("text", "query")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    QUERY_FIELD_NUMBER: _ClassVar[int]
    text: str
    query: bool
    def __init__(self, text: _Optional[str] = ..., query: bool = ...) -> None: ...

class EmbeddingRequest(_message.Message):
    __slots__ = ("embeddables", "model_uuid")
    EMBEDDABLES_FIELD_NUMBER: _ClassVar[int]
    MODEL_UUID_FIELD_NUMBER: _ClassVar[int]
    embeddables: _containers.RepeatedCompositeFieldContainer[Embeddable]
    model_uuid: str
    def __init__(self, embeddables: _Optional[_Iterable[_Union[Embeddable, _Mapping]]] = ..., model_uuid: _Optional[str] = ...) -> None: ...

class EmbeddingResponse(_message.Message):
    __slots__ = ("embeddings", "dim", "dtype_size")
    EMBEDDINGS_FIELD_NUMBER: _ClassVar[int]
    DIM_FIELD_NUMBER: _ClassVar[int]
    DTYPE_SIZE_FIELD_NUMBER: _ClassVar[int]
    embeddings: _containers.RepeatedScalarFieldContainer[bytes]
    dim: int
    dtype_size: int
    def __init__(self, embeddings: _Optional[_Iterable[bytes]] = ..., dim: _Optional[int] = ..., dtype_size: _Optional[int] = ...) -> None: ...
