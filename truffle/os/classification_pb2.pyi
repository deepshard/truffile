from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ClassifyRequest(_message.Message):
    __slots__ = ("prompt", "max_results")
    PROMPT_FIELD_NUMBER: _ClassVar[int]
    MAX_RESULTS_FIELD_NUMBER: _ClassVar[int]
    prompt: str
    max_results: int
    def __init__(self, prompt: _Optional[str] = ..., max_results: _Optional[int] = ...) -> None: ...

class ClassifyResponse(_message.Message):
    __slots__ = ("results",)
    class ClassifyResult(_message.Message):
        __slots__ = ("app_id", "score")
        APP_ID_FIELD_NUMBER: _ClassVar[int]
        SCORE_FIELD_NUMBER: _ClassVar[int]
        app_id: str
        score: float
        def __init__(self, app_id: _Optional[str] = ..., score: _Optional[float] = ...) -> None: ...
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[ClassifyResponse.ClassifyResult]
    def __init__(self, results: _Optional[_Iterable[_Union[ClassifyResponse.ClassifyResult, _Mapping]]] = ...) -> None: ...
