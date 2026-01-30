from truffle.os import task_info_pb2 as _task_info_pb2
from truffle.os import task_pb2 as _task_pb2
from truffle.os import task_info_pb2 as _task_info_pb2_1
from truffle.os import task_user_response_pb2 as _task_user_response_pb2
from truffle.os import task_step_pb2 as _task_step_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetTasksRequest(_message.Message):
    __slots__ = ("task_ids", "with_nodes")
    TASK_IDS_FIELD_NUMBER: _ClassVar[int]
    WITH_NODES_FIELD_NUMBER: _ClassVar[int]
    task_ids: _containers.RepeatedScalarFieldContainer[str]
    with_nodes: bool
    def __init__(self, task_ids: _Optional[_Iterable[str]] = ..., with_nodes: bool = ...) -> None: ...

class GetOneTaskRequest(_message.Message):
    __slots__ = ("task_id", "with_nodes")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    WITH_NODES_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    with_nodes: bool
    def __init__(self, task_id: _Optional[str] = ..., with_nodes: bool = ...) -> None: ...

class GetTaskInfosRequest(_message.Message):
    __slots__ = ("target_task_id", "max_before", "max_after")
    TARGET_TASK_ID_FIELD_NUMBER: _ClassVar[int]
    MAX_BEFORE_FIELD_NUMBER: _ClassVar[int]
    MAX_AFTER_FIELD_NUMBER: _ClassVar[int]
    target_task_id: str
    max_before: int
    max_after: int
    def __init__(self, target_task_id: _Optional[str] = ..., max_before: _Optional[int] = ..., max_after: _Optional[int] = ...) -> None: ...

class GetTaskInfosResponse(_message.Message):
    __slots__ = ("entries", "total_num_tasks")
    class TaskPreview(_message.Message):
        __slots__ = ("task_id", "info", "last_node")
        TASK_ID_FIELD_NUMBER: _ClassVar[int]
        INFO_FIELD_NUMBER: _ClassVar[int]
        LAST_NODE_FIELD_NUMBER: _ClassVar[int]
        task_id: str
        info: _task_info_pb2_1.TaskInfo
        last_node: _task_pb2.TaskNode
        def __init__(self, task_id: _Optional[str] = ..., info: _Optional[_Union[_task_info_pb2_1.TaskInfo, _Mapping]] = ..., last_node: _Optional[_Union[_task_pb2.TaskNode, _Mapping]] = ...) -> None: ...
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    TOTAL_NUM_TASKS_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[GetTaskInfosResponse.TaskPreview]
    total_num_tasks: int
    def __init__(self, entries: _Optional[_Iterable[_Union[GetTaskInfosResponse.TaskPreview, _Mapping]]] = ..., total_num_tasks: _Optional[int] = ...) -> None: ...
