from google.protobuf import timestamp_pb2 as _timestamp_pb2
from truffle.common import file_pb2 as _file_pb2
from truffle.os import task_info_pb2 as _task_info_pb2
from truffle.os import task_user_response_pb2 as _task_user_response_pb2
from truffle.os import task_step_pb2 as _task_step_pb2
from truffle.common import content_pb2 as _content_pb2
from truffle.os import task_error_pb2 as _task_error_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union
from truffle.os.task_info_pb2 import TaskInfo as TaskInfo
from truffle.os.task_info_pb2 import TaskFlags as TaskFlags
from truffle.os.task_user_response_pb2 import UserMessage as UserMessage
from truffle.os.task_user_response_pb2 import PendingUserResponse as PendingUserResponse
from truffle.os.task_user_response_pb2 import RespondToTaskRequest as RespondToTaskRequest
from truffle.os.task_step_pb2 import Step as Step

DESCRIPTOR: _descriptor.FileDescriptor
TASK_FLAGS_NONE: _task_info_pb2.TaskFlags
TASK_ACTIVE: _task_info_pb2.TaskFlags
TASK_NO_RESPOND: _task_info_pb2.TaskFlags
TASK_BLOCKED: _task_info_pb2.TaskFlags

class Task(_message.Message):
    __slots__ = ("task_id", "info", "task_flags", "nodes")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    INFO_FIELD_NUMBER: _ClassVar[int]
    TASK_FLAGS_FIELD_NUMBER: _ClassVar[int]
    NODES_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    info: _task_info_pb2.TaskInfo
    task_flags: int
    nodes: _containers.RepeatedCompositeFieldContainer[TaskNode]
    def __init__(self, task_id: _Optional[str] = ..., info: _Optional[_Union[_task_info_pb2.TaskInfo, _Mapping]] = ..., task_flags: _Optional[int] = ..., nodes: _Optional[_Iterable[_Union[TaskNode, _Mapping]]] = ...) -> None: ...

class TasksList(_message.Message):
    __slots__ = ("tasks",)
    TASKS_FIELD_NUMBER: _ClassVar[int]
    tasks: _containers.RepeatedCompositeFieldContainer[Task]
    def __init__(self, tasks: _Optional[_Iterable[_Union[Task, _Mapping]]] = ...) -> None: ...

class TaskNode(_message.Message):
    __slots__ = ("id", "parent_id", "child_ids", "files", "step", "user_msg")
    ID_FIELD_NUMBER: _ClassVar[int]
    PARENT_ID_FIELD_NUMBER: _ClassVar[int]
    CHILD_IDS_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    STEP_FIELD_NUMBER: _ClassVar[int]
    USER_MSG_FIELD_NUMBER: _ClassVar[int]
    id: int
    parent_id: int
    child_ids: _containers.RepeatedScalarFieldContainer[int]
    files: _containers.RepeatedCompositeFieldContainer[_file_pb2.AttachedFile]
    step: _task_step_pb2.Step
    user_msg: _task_user_response_pb2.UserMessage
    def __init__(self, id: _Optional[int] = ..., parent_id: _Optional[int] = ..., child_ids: _Optional[_Iterable[int]] = ..., files: _Optional[_Iterable[_Union[_file_pb2.AttachedFile, _Mapping]]] = ..., step: _Optional[_Union[_task_step_pb2.Step, _Mapping]] = ..., user_msg: _Optional[_Union[_task_user_response_pb2.UserMessage, _Mapping]] = ...) -> None: ...

class TaskStreamUpdate(_message.Message):
    __slots__ = ("task_id", "info", "nodes", "error")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    INFO_FIELD_NUMBER: _ClassVar[int]
    NODES_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    info: _task_info_pb2.TaskInfo
    nodes: _containers.RepeatedCompositeFieldContainer[TaskNode]
    error: _task_error_pb2.TaskError
    def __init__(self, task_id: _Optional[str] = ..., info: _Optional[_Union[_task_info_pb2.TaskInfo, _Mapping]] = ..., nodes: _Optional[_Iterable[_Union[TaskNode, _Mapping]]] = ..., error: _Optional[_Union[_task_error_pb2.TaskError, _Mapping]] = ...) -> None: ...
