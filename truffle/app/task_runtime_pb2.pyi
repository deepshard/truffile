from truffle.os import task_pb2 as _task_pb2
from truffle.os import task_info_pb2 as _task_info_pb2
from truffle.os import task_user_response_pb2 as _task_user_response_pb2
from truffle.os import task_step_pb2 as _task_step_pb2
from truffle.os import task_user_response_pb2 as _task_user_response_pb2_1
from truffle.os import task_actions_pb2 as _task_actions_pb2
from truffle.os import task_pb2 as _task_pb2_1
from truffle.os import task_target_pb2 as _task_target_pb2
from truffle.os import task_options_pb2 as _task_options_pb2
from truffle.os import task_user_response_pb2 as _task_user_response_pb2_1_1
from truffle.common import tool_provider_pb2 as _tool_provider_pb2
from truffle.os import task_step_pb2 as _task_step_pb2_1
from truffle.common import content_pb2 as _content_pb2
from truffle.infer.convo import conversation_pb2 as _conversation_pb2
from truffle.infer.convo import msg_pb2 as _msg_pb2
from truffle.app import background_feed_pb2 as _background_feed_pb2
from truffle.common import file_pb2 as _file_pb2
from truffle.os import task_options_pb2 as _task_options_pb2_1
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ToolsProvider(_message.Message):
    __slots__ = ("mcp_server",)
    class MCPServer(_message.Message):
        __slots__ = ("uuid", "address", "port", "path")
        UUID_FIELD_NUMBER: _ClassVar[int]
        ADDRESS_FIELD_NUMBER: _ClassVar[int]
        PORT_FIELD_NUMBER: _ClassVar[int]
        PATH_FIELD_NUMBER: _ClassVar[int]
        uuid: str
        address: str
        port: int
        path: str
        def __init__(self, uuid: _Optional[str] = ..., address: _Optional[str] = ..., port: _Optional[int] = ..., path: _Optional[str] = ...) -> None: ...
    MCP_SERVER_FIELD_NUMBER: _ClassVar[int]
    mcp_server: ToolsProvider.MCPServer
    def __init__(self, mcp_server: _Optional[_Union[ToolsProvider.MCPServer, _Mapping]] = ...) -> None: ...

class AddToolProviderRequest(_message.Message):
    __slots__ = ("tool_provider",)
    TOOL_PROVIDER_FIELD_NUMBER: _ClassVar[int]
    tool_provider: ToolsProvider
    def __init__(self, tool_provider: _Optional[_Union[ToolsProvider, _Mapping]] = ...) -> None: ...

class AddToolProviderResponse(_message.Message):
    __slots__ = ("current_tool_providers",)
    CURRENT_TOOL_PROVIDERS_FIELD_NUMBER: _ClassVar[int]
    current_tool_providers: _containers.RepeatedCompositeFieldContainer[ToolsProvider]
    def __init__(self, current_tool_providers: _Optional[_Iterable[_Union[ToolsProvider, _Mapping]]] = ...) -> None: ...

class RemoveToolProviderRequest(_message.Message):
    __slots__ = ("provider_uuid",)
    PROVIDER_UUID_FIELD_NUMBER: _ClassVar[int]
    provider_uuid: str
    def __init__(self, provider_uuid: _Optional[str] = ...) -> None: ...

class RemoveToolProviderResponse(_message.Message):
    __slots__ = ("current_tool_providers",)
    CURRENT_TOOL_PROVIDERS_FIELD_NUMBER: _ClassVar[int]
    current_tool_providers: _containers.RepeatedCompositeFieldContainer[ToolsProvider]
    def __init__(self, current_tool_providers: _Optional[_Iterable[_Union[ToolsProvider, _Mapping]]] = ...) -> None: ...

class TaskContextUpdate(_message.Message):
    __slots__ = ("latest_convo", "associated_node_id")
    LATEST_CONVO_FIELD_NUMBER: _ClassVar[int]
    ASSOCIATED_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    latest_convo: _conversation_pb2.Conversation
    associated_node_id: int
    def __init__(self, latest_convo: _Optional[_Union[_conversation_pb2.Conversation, _Mapping]] = ..., associated_node_id: _Optional[int] = ...) -> None: ...

class NewTask(_message.Message):
    __slots__ = ("user_message", "attached_files", "attached_feed_entries")
    USER_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    ATTACHED_FILES_FIELD_NUMBER: _ClassVar[int]
    ATTACHED_FEED_ENTRIES_FIELD_NUMBER: _ClassVar[int]
    user_message: _task_user_response_pb2_1_1.UserMessage
    attached_files: _containers.RepeatedCompositeFieldContainer[_file_pb2.AttachedFileIntent]
    attached_feed_entries: _background_feed_pb2.FeedEntryTaskContext
    def __init__(self, user_message: _Optional[_Union[_task_user_response_pb2_1_1.UserMessage, _Mapping]] = ..., attached_files: _Optional[_Iterable[_Union[_file_pb2.AttachedFileIntent, _Mapping]]] = ..., attached_feed_entries: _Optional[_Union[_background_feed_pb2.FeedEntryTaskContext, _Mapping]] = ...) -> None: ...

class PrevTask(_message.Message):
    __slots__ = ("task", "latest_context")
    TASK_FIELD_NUMBER: _ClassVar[int]
    LATEST_CONTEXT_FIELD_NUMBER: _ClassVar[int]
    task: _task_pb2_1.Task
    latest_context: TaskContextUpdate
    def __init__(self, task: _Optional[_Union[_task_pb2_1.Task, _Mapping]] = ..., latest_context: _Optional[_Union[TaskContextUpdate, _Mapping]] = ...) -> None: ...

class StartTaskRequest(_message.Message):
    __slots__ = ("new_task", "prev_task", "options", "tool_providers")
    NEW_TASK_FIELD_NUMBER: _ClassVar[int]
    PREV_TASK_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    TOOL_PROVIDERS_FIELD_NUMBER: _ClassVar[int]
    new_task: NewTask
    prev_task: PrevTask
    options: _task_options_pb2_1.TaskOptions
    tool_providers: _containers.RepeatedCompositeFieldContainer[ToolsProvider]
    def __init__(self, new_task: _Optional[_Union[NewTask, _Mapping]] = ..., prev_task: _Optional[_Union[PrevTask, _Mapping]] = ..., options: _Optional[_Union[_task_options_pb2_1.TaskOptions, _Mapping]] = ..., tool_providers: _Optional[_Iterable[_Union[ToolsProvider, _Mapping]]] = ...) -> None: ...

class TaskRuntimeError(_message.Message):
    __slots__ = ("error", "details", "associated_provider_uuid")
    ERROR_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    ASSOCIATED_PROVIDER_UUID_FIELD_NUMBER: _ClassVar[int]
    error: str
    details: str
    associated_provider_uuid: str
    def __init__(self, error: _Optional[str] = ..., details: _Optional[str] = ..., associated_provider_uuid: _Optional[str] = ...) -> None: ...

class TaskRuntimeUpdate(_message.Message):
    __slots__ = ("task_update", "runtime_error", "context_update")
    TASK_UPDATE_FIELD_NUMBER: _ClassVar[int]
    RUNTIME_ERROR_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_UPDATE_FIELD_NUMBER: _ClassVar[int]
    task_update: _task_pb2_1.TaskStreamUpdate
    runtime_error: TaskRuntimeError
    context_update: TaskContextUpdate
    def __init__(self, task_update: _Optional[_Union[_task_pb2_1.TaskStreamUpdate, _Mapping]] = ..., runtime_error: _Optional[_Union[TaskRuntimeError, _Mapping]] = ..., context_update: _Optional[_Union[TaskContextUpdate, _Mapping]] = ...) -> None: ...
