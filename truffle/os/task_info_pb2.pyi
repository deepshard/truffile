from google.protobuf import timestamp_pb2 as _timestamp_pb2
from truffle.os import task_options_pb2 as _task_options_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TaskFlags(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TASK_FLAGS_NONE: _ClassVar[TaskFlags]
    TASK_ACTIVE: _ClassVar[TaskFlags]
    TASK_NO_RESPOND: _ClassVar[TaskFlags]
    TASK_BLOCKED: _ClassVar[TaskFlags]
TASK_FLAGS_NONE: TaskFlags
TASK_ACTIVE: TaskFlags
TASK_NO_RESPOND: TaskFlags
TASK_BLOCKED: TaskFlags

class TaskInfo(_message.Message):
    __slots__ = ("run_state", "app_uuids", "task_title", "options", "created", "last_updated", "access_uri")
    class TaskRunState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        TASK_RUN_STATE_INVALID: _ClassVar[TaskInfo.TaskRunState]
        TASK_RUN_STATE_CREATING_NEW: _ClassVar[TaskInfo.TaskRunState]
        TASK_RUN_STATE_RELOADING_PREV: _ClassVar[TaskInfo.TaskRunState]
        TASK_RUN_STATE_READY: _ClassVar[TaskInfo.TaskRunState]
        TASK_RUN_STATE_FATAL_ERROR: _ClassVar[TaskInfo.TaskRunState]
    TASK_RUN_STATE_INVALID: TaskInfo.TaskRunState
    TASK_RUN_STATE_CREATING_NEW: TaskInfo.TaskRunState
    TASK_RUN_STATE_RELOADING_PREV: TaskInfo.TaskRunState
    TASK_RUN_STATE_READY: TaskInfo.TaskRunState
    TASK_RUN_STATE_FATAL_ERROR: TaskInfo.TaskRunState
    RUN_STATE_FIELD_NUMBER: _ClassVar[int]
    APP_UUIDS_FIELD_NUMBER: _ClassVar[int]
    TASK_TITLE_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    CREATED_FIELD_NUMBER: _ClassVar[int]
    LAST_UPDATED_FIELD_NUMBER: _ClassVar[int]
    ACCESS_URI_FIELD_NUMBER: _ClassVar[int]
    run_state: TaskInfo.TaskRunState
    app_uuids: _containers.RepeatedScalarFieldContainer[str]
    task_title: str
    options: _task_options_pb2.TaskOptions
    created: _timestamp_pb2.Timestamp
    last_updated: _timestamp_pb2.Timestamp
    access_uri: str
    def __init__(self, run_state: _Optional[_Union[TaskInfo.TaskRunState, str]] = ..., app_uuids: _Optional[_Iterable[str]] = ..., task_title: _Optional[str] = ..., options: _Optional[_Union[_task_options_pb2.TaskOptions, _Mapping]] = ..., created: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., last_updated: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., access_uri: _Optional[str] = ...) -> None: ...
