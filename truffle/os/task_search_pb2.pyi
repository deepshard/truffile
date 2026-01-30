from google.protobuf import timestamp_pb2 as _timestamp_pb2
from truffle.os import task_info_pb2 as _task_info_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SearchTasksRequest(_message.Message):
    __slots__ = ("query", "max_results", "offset")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    MAX_RESULTS_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    query: str
    max_results: int
    offset: int
    def __init__(self, query: _Optional[str] = ..., max_results: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class TaskSearchResult(_message.Message):
    __slots__ = ("task_id", "task_info", "timestamp", "content")
    class TaskSearchContent(_message.Message):
        __slots__ = ("snippet",)
        SNIPPET_FIELD_NUMBER: _ClassVar[int]
        snippet: str
        def __init__(self, snippet: _Optional[str] = ...) -> None: ...
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    TASK_INFO_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    task_info: _task_info_pb2.TaskInfo
    timestamp: _timestamp_pb2.Timestamp
    content: TaskSearchResult.TaskSearchContent
    def __init__(self, task_id: _Optional[str] = ..., task_info: _Optional[_Union[_task_info_pb2.TaskInfo, _Mapping]] = ..., timestamp: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., content: _Optional[_Union[TaskSearchResult.TaskSearchContent, _Mapping]] = ...) -> None: ...

class SearchTasksResponse(_message.Message):
    __slots__ = ("total_results", "current_offset", "results")
    TOTAL_RESULTS_FIELD_NUMBER: _ClassVar[int]
    CURRENT_OFFSET_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    total_results: int
    current_offset: int
    results: _containers.RepeatedCompositeFieldContainer[TaskSearchResult]
    def __init__(self, total_results: _Optional[int] = ..., current_offset: _Optional[int] = ..., results: _Optional[_Iterable[_Union[TaskSearchResult, _Mapping]]] = ...) -> None: ...
