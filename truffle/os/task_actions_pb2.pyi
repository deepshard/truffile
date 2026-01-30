from truffle.common import file_pb2 as _file_pb2
from truffle.os import task_pb2 as _task_pb2
from truffle.os import task_info_pb2 as _task_info_pb2
from truffle.os import task_user_response_pb2 as _task_user_response_pb2
from truffle.os import task_step_pb2 as _task_step_pb2
from truffle.os import task_target_pb2 as _task_target_pb2
from truffle.os import task_options_pb2 as _task_options_pb2
from truffle.os import task_user_response_pb2 as _task_user_response_pb2_1
from truffle.common import tool_provider_pb2 as _tool_provider_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union
from truffle.os.task_pb2 import Task as Task
from truffle.os.task_pb2 import TasksList as TasksList
from truffle.os.task_pb2 import TaskNode as TaskNode
from truffle.os.task_pb2 import TaskStreamUpdate as TaskStreamUpdate
from truffle.os.task_target_pb2 import TargetTask as TargetTask
from truffle.os.task_options_pb2 import TaskOptions as TaskOptions
from truffle.os.task_user_response_pb2 import UserMessage as UserMessage
from truffle.os.task_user_response_pb2 import PendingUserResponse as PendingUserResponse
from truffle.os.task_user_response_pb2 import RespondToTaskRequest as RespondToTaskRequest
from truffle.common.tool_provider_pb2 import ExternalToolProvider as ExternalToolProvider
from truffle.common.tool_provider_pb2 import ExternalToolProvidersError as ExternalToolProvidersError

DESCRIPTOR: _descriptor.FileDescriptor

class InterruptTaskRequest(_message.Message):
    __slots__ = ("target",)
    TARGET_FIELD_NUMBER: _ClassVar[int]
    target: _task_target_pb2.TargetTask
    def __init__(self, target: _Optional[_Union[_task_target_pb2.TargetTask, _Mapping]] = ...) -> None: ...

class NewTask(_message.Message):
    __slots__ = ("user_message", "app_uuids", "files_to_be_uploaded")
    USER_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    APP_UUIDS_FIELD_NUMBER: _ClassVar[int]
    FILES_TO_BE_UPLOADED_FIELD_NUMBER: _ClassVar[int]
    user_message: _task_user_response_pb2_1.UserMessage
    app_uuids: _containers.RepeatedScalarFieldContainer[str]
    files_to_be_uploaded: _containers.RepeatedCompositeFieldContainer[_file_pb2.AttachedFileIntent]
    def __init__(self, user_message: _Optional[_Union[_task_user_response_pb2_1.UserMessage, _Mapping]] = ..., app_uuids: _Optional[_Iterable[str]] = ..., files_to_be_uploaded: _Optional[_Iterable[_Union[_file_pb2.AttachedFileIntent, _Mapping]]] = ...) -> None: ...

class OpenTaskRequest(_message.Message):
    __slots__ = ("existing_task", "new_task", "options", "external_tool_providers")
    EXISTING_TASK_FIELD_NUMBER: _ClassVar[int]
    NEW_TASK_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_TOOL_PROVIDERS_FIELD_NUMBER: _ClassVar[int]
    existing_task: _task_target_pb2.TargetTask
    new_task: NewTask
    options: _task_options_pb2.TaskOptions
    external_tool_providers: _containers.RepeatedCompositeFieldContainer[_tool_provider_pb2.ExternalToolProvider]
    def __init__(self, existing_task: _Optional[_Union[_task_target_pb2.TargetTask, _Mapping]] = ..., new_task: _Optional[_Union[NewTask, _Mapping]] = ..., options: _Optional[_Union[_task_options_pb2.TaskOptions, _Mapping]] = ..., external_tool_providers: _Optional[_Iterable[_Union[_tool_provider_pb2.ExternalToolProvider, _Mapping]]] = ...) -> None: ...

class TaskSetAvailableAppsRequest(_message.Message):
    __slots__ = ("task_id", "app_uuids", "external_tool_providers")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    APP_UUIDS_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_TOOL_PROVIDERS_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    app_uuids: _containers.RepeatedScalarFieldContainer[str]
    external_tool_providers: _containers.RepeatedCompositeFieldContainer[_tool_provider_pb2.ExternalToolProvider]
    def __init__(self, task_id: _Optional[str] = ..., app_uuids: _Optional[_Iterable[str]] = ..., external_tool_providers: _Optional[_Iterable[_Union[_tool_provider_pb2.ExternalToolProvider, _Mapping]]] = ...) -> None: ...

class TaskSetAvailableAppsResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class TaskActionResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class TaskTestExternalToolProviderRequest(_message.Message):
    __slots__ = ("external_tool_provider",)
    EXTERNAL_TOOL_PROVIDER_FIELD_NUMBER: _ClassVar[int]
    external_tool_provider: _tool_provider_pb2.ExternalToolProvider
    def __init__(self, external_tool_provider: _Optional[_Union[_tool_provider_pb2.ExternalToolProvider, _Mapping]] = ...) -> None: ...

class TaskTestExternalToolProviderResponse(_message.Message):
    __slots__ = ("success", "error_message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error_message: str
    def __init__(self, success: bool = ..., error_message: _Optional[str] = ...) -> None: ...
