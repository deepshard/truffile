import datetime

from truffle.common import file_pb2 as _file_pb2
from truffle.common import content_pb2 as _content_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ConvoUserBlock(_message.Message):
    __slots__ = ("content", "seen_at")
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    SEEN_AT_FIELD_NUMBER: _ClassVar[int]
    content: str
    seen_at: _timestamp_pb2.Timestamp
    def __init__(self, content: _Optional[str] = ..., seen_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ConvoAgentBlock(_message.Message):
    __slots__ = ("block_id", "sub_blocks", "reply", "tool_calls", "thoughts", "extra")
    class AgentReply(_message.Message):
        __slots__ = ("content",)
        CONTENT_FIELD_NUMBER: _ClassVar[int]
        content: str
        def __init__(self, content: _Optional[str] = ...) -> None: ...
    class AgentToolCall(_message.Message):
        __slots__ = ("tool_name", "raw_args", "timestamp_offset_s", "raw_response", "tool_id")
        TOOL_NAME_FIELD_NUMBER: _ClassVar[int]
        RAW_ARGS_FIELD_NUMBER: _ClassVar[int]
        TIMESTAMP_OFFSET_S_FIELD_NUMBER: _ClassVar[int]
        RAW_RESPONSE_FIELD_NUMBER: _ClassVar[int]
        TOOL_ID_FIELD_NUMBER: _ClassVar[int]
        tool_name: str
        raw_args: str
        timestamp_offset_s: float
        raw_response: str
        tool_id: str
        def __init__(self, tool_name: _Optional[str] = ..., raw_args: _Optional[str] = ..., timestamp_offset_s: _Optional[float] = ..., raw_response: _Optional[str] = ..., tool_id: _Optional[str] = ...) -> None: ...
    class AgentThought(_message.Message):
        __slots__ = ("content", "timestamp_offset_s")
        CONTENT_FIELD_NUMBER: _ClassVar[int]
        TIMESTAMP_OFFSET_S_FIELD_NUMBER: _ClassVar[int]
        content: str
        timestamp_offset_s: float
        def __init__(self, content: _Optional[str] = ..., timestamp_offset_s: _Optional[float] = ...) -> None: ...
    BLOCK_ID_FIELD_NUMBER: _ClassVar[int]
    SUB_BLOCKS_FIELD_NUMBER: _ClassVar[int]
    REPLY_FIELD_NUMBER: _ClassVar[int]
    TOOL_CALLS_FIELD_NUMBER: _ClassVar[int]
    THOUGHTS_FIELD_NUMBER: _ClassVar[int]
    EXTRA_FIELD_NUMBER: _ClassVar[int]
    block_id: int
    sub_blocks: _containers.RepeatedCompositeFieldContainer[ConvoAgentBlock]
    reply: ConvoAgentBlock.AgentReply
    tool_calls: _containers.RepeatedCompositeFieldContainer[ConvoAgentBlock.AgentToolCall]
    thoughts: _containers.RepeatedCompositeFieldContainer[ConvoAgentBlock.AgentThought]
    extra: _struct_pb2.Struct
    def __init__(self, block_id: _Optional[int] = ..., sub_blocks: _Optional[_Iterable[_Union[ConvoAgentBlock, _Mapping]]] = ..., reply: _Optional[_Union[ConvoAgentBlock.AgentReply, _Mapping]] = ..., tool_calls: _Optional[_Iterable[_Union[ConvoAgentBlock.AgentToolCall, _Mapping]]] = ..., thoughts: _Optional[_Iterable[_Union[ConvoAgentBlock.AgentThought, _Mapping]]] = ..., extra: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class ConvoNodeRef(_message.Message):
    __slots__ = ("thread_id", "node_id")
    THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    thread_id: int
    node_id: int
    def __init__(self, thread_id: _Optional[int] = ..., node_id: _Optional[int] = ...) -> None: ...

class ConvoNodeOrigin(_message.Message):
    __slots__ = ("kind", "source")
    class OriginKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        ORIGIN_KIND_UNSPECIFIED: _ClassVar[ConvoNodeOrigin.OriginKind]
        ORIGIN_KIND_THREAD_TO_PARENT_MESSAGE: _ClassVar[ConvoNodeOrigin.OriginKind]
        ORIGIN_KIND_BACKGROUND_SUBMISSION: _ClassVar[ConvoNodeOrigin.OriginKind]
        ORIGIN_KIND_SCHEDULE_RUN: _ClassVar[ConvoNodeOrigin.OriginKind]
        ORIGIN_KIND_RUNTIME_EVENT: _ClassVar[ConvoNodeOrigin.OriginKind]
        ORIGIN_KIND_USER_FORWARD: _ClassVar[ConvoNodeOrigin.OriginKind]
        ORIGIN_KIND_ACTION_RESULT: _ClassVar[ConvoNodeOrigin.OriginKind]
    ORIGIN_KIND_UNSPECIFIED: ConvoNodeOrigin.OriginKind
    ORIGIN_KIND_THREAD_TO_PARENT_MESSAGE: ConvoNodeOrigin.OriginKind
    ORIGIN_KIND_BACKGROUND_SUBMISSION: ConvoNodeOrigin.OriginKind
    ORIGIN_KIND_SCHEDULE_RUN: ConvoNodeOrigin.OriginKind
    ORIGIN_KIND_RUNTIME_EVENT: ConvoNodeOrigin.OriginKind
    ORIGIN_KIND_USER_FORWARD: ConvoNodeOrigin.OriginKind
    ORIGIN_KIND_ACTION_RESULT: ConvoNodeOrigin.OriginKind
    KIND_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    kind: ConvoNodeOrigin.OriginKind
    source: ConvoNodeRef
    def __init__(self, kind: _Optional[_Union[ConvoNodeOrigin.OriginKind, str]] = ..., source: _Optional[_Union[ConvoNodeRef, _Mapping]] = ...) -> None: ...

class ConvoReference(_message.Message):
    __slots__ = ("label", "convo", "app", "url", "schedule", "memory", "thread")
    class ConvoAppRef(_message.Message):
        __slots__ = ("app_uuid",)
        APP_UUID_FIELD_NUMBER: _ClassVar[int]
        app_uuid: str
        def __init__(self, app_uuid: _Optional[str] = ...) -> None: ...
    class ConvoUrlRef(_message.Message):
        __slots__ = ("url",)
        URL_FIELD_NUMBER: _ClassVar[int]
        url: str
        def __init__(self, url: _Optional[str] = ...) -> None: ...
    class ConvoScheduleRef(_message.Message):
        __slots__ = ("schedule_id",)
        SCHEDULE_ID_FIELD_NUMBER: _ClassVar[int]
        schedule_id: str
        def __init__(self, schedule_id: _Optional[str] = ...) -> None: ...
    class ConvoMemoryRef(_message.Message):
        __slots__ = ("memory_id",)
        MEMORY_ID_FIELD_NUMBER: _ClassVar[int]
        memory_id: str
        def __init__(self, memory_id: _Optional[str] = ...) -> None: ...
    class ConvoThreadRef(_message.Message):
        __slots__ = ("thread_id",)
        THREAD_ID_FIELD_NUMBER: _ClassVar[int]
        thread_id: int
        def __init__(self, thread_id: _Optional[int] = ...) -> None: ...
    LABEL_FIELD_NUMBER: _ClassVar[int]
    CONVO_FIELD_NUMBER: _ClassVar[int]
    APP_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    SCHEDULE_FIELD_NUMBER: _ClassVar[int]
    MEMORY_FIELD_NUMBER: _ClassVar[int]
    THREAD_FIELD_NUMBER: _ClassVar[int]
    label: str
    convo: ConvoNodeRef
    app: ConvoReference.ConvoAppRef
    url: ConvoReference.ConvoUrlRef
    schedule: ConvoReference.ConvoScheduleRef
    memory: ConvoReference.ConvoMemoryRef
    thread: ConvoReference.ConvoThreadRef
    def __init__(self, label: _Optional[str] = ..., convo: _Optional[_Union[ConvoNodeRef, _Mapping]] = ..., app: _Optional[_Union[ConvoReference.ConvoAppRef, _Mapping]] = ..., url: _Optional[_Union[ConvoReference.ConvoUrlRef, _Mapping]] = ..., schedule: _Optional[_Union[ConvoReference.ConvoScheduleRef, _Mapping]] = ..., memory: _Optional[_Union[ConvoReference.ConvoMemoryRef, _Mapping]] = ..., thread: _Optional[_Union[ConvoReference.ConvoThreadRef, _Mapping]] = ...) -> None: ...

class ConvoSystemBlock(_message.Message):
    __slots__ = ("inbox_event", "system_event", "extra")
    class InboxEvent(_message.Message):
        __slots__ = ("event_type", "source_label", "title", "content", "sent_at", "origin", "references")
        class InboxEventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            INBOX_EVENT_DEFAULT: _ClassVar[ConvoSystemBlock.InboxEvent.InboxEventType]
            INBOX_EVENT_AGENT_MESSAGE: _ClassVar[ConvoSystemBlock.InboxEvent.InboxEventType]
            INBOX_EVENT_SCHEDULED_TASK: _ClassVar[ConvoSystemBlock.InboxEvent.InboxEventType]
            INBOX_EVENT_SOURCE_AGENT: _ClassVar[ConvoSystemBlock.InboxEvent.InboxEventType]
            INBOX_EVENT_SOURCE_BACKGROUND: _ClassVar[ConvoSystemBlock.InboxEvent.InboxEventType]
            INBOX_EVENT_SOURCE_SCHEDULE: _ClassVar[ConvoSystemBlock.InboxEvent.InboxEventType]
            INBOX_EVENT_SOURCE_SYSTEM: _ClassVar[ConvoSystemBlock.InboxEvent.InboxEventType]
            INBOX_EVENT_SOURCE_RUNTIME: _ClassVar[ConvoSystemBlock.InboxEvent.InboxEventType]
            INBOX_EVENT_SOURCE_INTERNAL: _ClassVar[ConvoSystemBlock.InboxEvent.InboxEventType]
            INBOX_EVENT_SOURCE_MEMORY: _ClassVar[ConvoSystemBlock.InboxEvent.InboxEventType]
        INBOX_EVENT_DEFAULT: ConvoSystemBlock.InboxEvent.InboxEventType
        INBOX_EVENT_AGENT_MESSAGE: ConvoSystemBlock.InboxEvent.InboxEventType
        INBOX_EVENT_SCHEDULED_TASK: ConvoSystemBlock.InboxEvent.InboxEventType
        INBOX_EVENT_SOURCE_AGENT: ConvoSystemBlock.InboxEvent.InboxEventType
        INBOX_EVENT_SOURCE_BACKGROUND: ConvoSystemBlock.InboxEvent.InboxEventType
        INBOX_EVENT_SOURCE_SCHEDULE: ConvoSystemBlock.InboxEvent.InboxEventType
        INBOX_EVENT_SOURCE_SYSTEM: ConvoSystemBlock.InboxEvent.InboxEventType
        INBOX_EVENT_SOURCE_RUNTIME: ConvoSystemBlock.InboxEvent.InboxEventType
        INBOX_EVENT_SOURCE_INTERNAL: ConvoSystemBlock.InboxEvent.InboxEventType
        INBOX_EVENT_SOURCE_MEMORY: ConvoSystemBlock.InboxEvent.InboxEventType
        EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
        SOURCE_LABEL_FIELD_NUMBER: _ClassVar[int]
        TITLE_FIELD_NUMBER: _ClassVar[int]
        CONTENT_FIELD_NUMBER: _ClassVar[int]
        SENT_AT_FIELD_NUMBER: _ClassVar[int]
        ORIGIN_FIELD_NUMBER: _ClassVar[int]
        REFERENCES_FIELD_NUMBER: _ClassVar[int]
        event_type: ConvoSystemBlock.InboxEvent.InboxEventType
        source_label: str
        title: str
        content: str
        sent_at: _timestamp_pb2.Timestamp
        origin: ConvoNodeOrigin
        references: _containers.RepeatedCompositeFieldContainer[ConvoReference]
        def __init__(self, event_type: _Optional[_Union[ConvoSystemBlock.InboxEvent.InboxEventType, str]] = ..., source_label: _Optional[str] = ..., title: _Optional[str] = ..., content: _Optional[str] = ..., sent_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., origin: _Optional[_Union[ConvoNodeOrigin, _Mapping]] = ..., references: _Optional[_Iterable[_Union[ConvoReference, _Mapping]]] = ...) -> None: ...
    class SystemEvent(_message.Message):
        __slots__ = ("event_type", "label", "started_at", "updated_at", "completed_at", "progress_percent")
        class SystemEventType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            SYSTEM_EVENT_INVALID: _ClassVar[ConvoSystemBlock.SystemEvent.SystemEventType]
            SYSTEM_EVENT_CONTEXT_COMPRESSION: _ClassVar[ConvoSystemBlock.SystemEvent.SystemEventType]
        SYSTEM_EVENT_INVALID: ConvoSystemBlock.SystemEvent.SystemEventType
        SYSTEM_EVENT_CONTEXT_COMPRESSION: ConvoSystemBlock.SystemEvent.SystemEventType
        EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
        LABEL_FIELD_NUMBER: _ClassVar[int]
        STARTED_AT_FIELD_NUMBER: _ClassVar[int]
        UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
        COMPLETED_AT_FIELD_NUMBER: _ClassVar[int]
        PROGRESS_PERCENT_FIELD_NUMBER: _ClassVar[int]
        event_type: ConvoSystemBlock.SystemEvent.SystemEventType
        label: str
        started_at: _timestamp_pb2.Timestamp
        updated_at: _timestamp_pb2.Timestamp
        completed_at: _timestamp_pb2.Timestamp
        progress_percent: int
        def __init__(self, event_type: _Optional[_Union[ConvoSystemBlock.SystemEvent.SystemEventType, str]] = ..., label: _Optional[str] = ..., started_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., completed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., progress_percent: _Optional[int] = ...) -> None: ...
    INBOX_EVENT_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_EVENT_FIELD_NUMBER: _ClassVar[int]
    EXTRA_FIELD_NUMBER: _ClassVar[int]
    inbox_event: ConvoSystemBlock.InboxEvent
    system_event: ConvoSystemBlock.SystemEvent
    extra: _struct_pb2.Struct
    def __init__(self, inbox_event: _Optional[_Union[ConvoSystemBlock.InboxEvent, _Mapping]] = ..., system_event: _Optional[_Union[ConvoSystemBlock.SystemEvent, _Mapping]] = ..., extra: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class ConvoErrorBlock(_message.Message):
    __slots__ = ("error",)
    ERROR_FIELD_NUMBER: _ClassVar[int]
    error: str
    def __init__(self, error: _Optional[str] = ...) -> None: ...

class ConvoActionBlock(_message.Message):
    __slots__ = ("kind", "status", "title", "body", "approve_label", "deny_label", "resolution", "start_agent_thread")
    class ActionKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        ACTION_KIND_UNSPECIFIED: _ClassVar[ConvoActionBlock.ActionKind]
        ACTION_KIND_START_AGENT_THREAD: _ClassVar[ConvoActionBlock.ActionKind]
    ACTION_KIND_UNSPECIFIED: ConvoActionBlock.ActionKind
    ACTION_KIND_START_AGENT_THREAD: ConvoActionBlock.ActionKind
    class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        STATUS_UNSPECIFIED: _ClassVar[ConvoActionBlock.Status]
        STATUS_PENDING: _ClassVar[ConvoActionBlock.Status]
        STATUS_APPROVED: _ClassVar[ConvoActionBlock.Status]
        STATUS_DENIED: _ClassVar[ConvoActionBlock.Status]
        STATUS_EXPIRED: _ClassVar[ConvoActionBlock.Status]
        STATUS_FAILED: _ClassVar[ConvoActionBlock.Status]
    STATUS_UNSPECIFIED: ConvoActionBlock.Status
    STATUS_PENDING: ConvoActionBlock.Status
    STATUS_APPROVED: ConvoActionBlock.Status
    STATUS_DENIED: ConvoActionBlock.Status
    STATUS_EXPIRED: ConvoActionBlock.Status
    STATUS_FAILED: ConvoActionBlock.Status
    class StartAgentThread(_message.Message):
        __slots__ = ("display_name", "description")
        DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
        DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
        display_name: str
        description: str
        def __init__(self, display_name: _Optional[str] = ..., description: _Optional[str] = ...) -> None: ...
    class Resolution(_message.Message):
        __slots__ = ("response_text", "resolved_at")
        RESPONSE_TEXT_FIELD_NUMBER: _ClassVar[int]
        RESOLVED_AT_FIELD_NUMBER: _ClassVar[int]
        response_text: str
        resolved_at: _timestamp_pb2.Timestamp
        def __init__(self, response_text: _Optional[str] = ..., resolved_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
    KIND_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    BODY_FIELD_NUMBER: _ClassVar[int]
    APPROVE_LABEL_FIELD_NUMBER: _ClassVar[int]
    DENY_LABEL_FIELD_NUMBER: _ClassVar[int]
    RESOLUTION_FIELD_NUMBER: _ClassVar[int]
    START_AGENT_THREAD_FIELD_NUMBER: _ClassVar[int]
    kind: ConvoActionBlock.ActionKind
    status: ConvoActionBlock.Status
    title: str
    body: str
    approve_label: str
    deny_label: str
    resolution: ConvoActionBlock.Resolution
    start_agent_thread: ConvoActionBlock.StartAgentThread
    def __init__(self, kind: _Optional[_Union[ConvoActionBlock.ActionKind, str]] = ..., status: _Optional[_Union[ConvoActionBlock.Status, str]] = ..., title: _Optional[str] = ..., body: _Optional[str] = ..., approve_label: _Optional[str] = ..., deny_label: _Optional[str] = ..., resolution: _Optional[_Union[ConvoActionBlock.Resolution, _Mapping]] = ..., start_agent_thread: _Optional[_Union[ConvoActionBlock.StartAgentThread, _Mapping]] = ...) -> None: ...

class ConvoInfo(_message.Message):
    __slots__ = ("access_uri", "stats")
    class ConvoStats(_message.Message):
        __slots__ = ("current_ctx_used", "current_ctx_remaining", "lifetime_tokens")
        CURRENT_CTX_USED_FIELD_NUMBER: _ClassVar[int]
        CURRENT_CTX_REMAINING_FIELD_NUMBER: _ClassVar[int]
        LIFETIME_TOKENS_FIELD_NUMBER: _ClassVar[int]
        current_ctx_used: int
        current_ctx_remaining: int
        lifetime_tokens: int
        def __init__(self, current_ctx_used: _Optional[int] = ..., current_ctx_remaining: _Optional[int] = ..., lifetime_tokens: _Optional[int] = ...) -> None: ...
    ACCESS_URI_FIELD_NUMBER: _ClassVar[int]
    STATS_FIELD_NUMBER: _ClassVar[int]
    access_uri: str
    stats: ConvoInfo.ConvoStats
    def __init__(self, access_uri: _Optional[str] = ..., stats: _Optional[_Union[ConvoInfo.ConvoStats, _Mapping]] = ...) -> None: ...

class ConvoNodeAttachments(_message.Message):
    __slots__ = ("files", "images")
    FILES_FIELD_NUMBER: _ClassVar[int]
    IMAGES_FIELD_NUMBER: _ClassVar[int]
    files: _containers.RepeatedCompositeFieldContainer[_file_pb2.AttachedFile]
    images: _containers.RepeatedCompositeFieldContainer[_content_pb2.AttachedImage]
    def __init__(self, files: _Optional[_Iterable[_Union[_file_pb2.AttachedFile, _Mapping]]] = ..., images: _Optional[_Iterable[_Union[_content_pb2.AttachedImage, _Mapping]]] = ...) -> None: ...

class ConvoNodeThreadInfo(_message.Message):
    __slots__ = ("thread_id", "thread_node_count")
    THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    THREAD_NODE_COUNT_FIELD_NUMBER: _ClassVar[int]
    thread_id: int
    thread_node_count: int
    def __init__(self, thread_id: _Optional[int] = ..., thread_node_count: _Optional[int] = ...) -> None: ...

class ConvoThreadInfo(_message.Message):
    __slots__ = ("thread_id", "runtime_thread_id", "display_name", "thread_kind", "parent_thread_id", "anchor_node_id", "node_count", "latest_node", "anchor_node", "display_name_source", "latest_node_id", "last_read_node_id", "unread_count", "has_unread")
    THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    RUNTIME_THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    THREAD_KIND_FIELD_NUMBER: _ClassVar[int]
    PARENT_THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    ANCHOR_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_COUNT_FIELD_NUMBER: _ClassVar[int]
    LATEST_NODE_FIELD_NUMBER: _ClassVar[int]
    ANCHOR_NODE_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_SOURCE_FIELD_NUMBER: _ClassVar[int]
    LATEST_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    LAST_READ_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    UNREAD_COUNT_FIELD_NUMBER: _ClassVar[int]
    HAS_UNREAD_FIELD_NUMBER: _ClassVar[int]
    thread_id: int
    runtime_thread_id: str
    display_name: str
    thread_kind: str
    parent_thread_id: int
    anchor_node_id: int
    node_count: int
    latest_node: ConvoNode
    anchor_node: ConvoNode
    display_name_source: str
    latest_node_id: int
    last_read_node_id: int
    unread_count: int
    has_unread: bool
    def __init__(self, thread_id: _Optional[int] = ..., runtime_thread_id: _Optional[str] = ..., display_name: _Optional[str] = ..., thread_kind: _Optional[str] = ..., parent_thread_id: _Optional[int] = ..., anchor_node_id: _Optional[int] = ..., node_count: _Optional[int] = ..., latest_node: _Optional[_Union[ConvoNode, _Mapping]] = ..., anchor_node: _Optional[_Union[ConvoNode, _Mapping]] = ..., display_name_source: _Optional[str] = ..., latest_node_id: _Optional[int] = ..., last_read_node_id: _Optional[int] = ..., unread_count: _Optional[int] = ..., has_unread: bool = ...) -> None: ...

class ConvoNode(_message.Message):
    __slots__ = ("id", "thread_id", "created_at", "attachments", "extra", "child_thread", "references", "origin", "user", "ai", "system", "error", "forward", "action")
    ID_FIELD_NUMBER: _ClassVar[int]
    THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    ATTACHMENTS_FIELD_NUMBER: _ClassVar[int]
    EXTRA_FIELD_NUMBER: _ClassVar[int]
    CHILD_THREAD_FIELD_NUMBER: _ClassVar[int]
    REFERENCES_FIELD_NUMBER: _ClassVar[int]
    ORIGIN_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    AI_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    FORWARD_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    id: int
    thread_id: int
    created_at: _timestamp_pb2.Timestamp
    attachments: ConvoNodeAttachments
    extra: _struct_pb2.Struct
    child_thread: ConvoNodeThreadInfo
    references: _containers.RepeatedCompositeFieldContainer[ConvoReference]
    origin: ConvoNodeOrigin
    user: ConvoUserBlock
    ai: ConvoAgentBlock
    system: ConvoSystemBlock
    error: ConvoErrorBlock
    forward: ConvoForwardBlock
    action: ConvoActionBlock
    def __init__(self, id: _Optional[int] = ..., thread_id: _Optional[int] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., attachments: _Optional[_Union[ConvoNodeAttachments, _Mapping]] = ..., extra: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., child_thread: _Optional[_Union[ConvoNodeThreadInfo, _Mapping]] = ..., references: _Optional[_Iterable[_Union[ConvoReference, _Mapping]]] = ..., origin: _Optional[_Union[ConvoNodeOrigin, _Mapping]] = ..., user: _Optional[_Union[ConvoUserBlock, _Mapping]] = ..., ai: _Optional[_Union[ConvoAgentBlock, _Mapping]] = ..., system: _Optional[_Union[ConvoSystemBlock, _Mapping]] = ..., error: _Optional[_Union[ConvoErrorBlock, _Mapping]] = ..., forward: _Optional[_Union[ConvoForwardBlock, _Mapping]] = ..., action: _Optional[_Union[ConvoActionBlock, _Mapping]] = ...) -> None: ...

class ConvoUpdateNotification(_message.Message):
    __slots__ = ("nodes", "convo_info", "threads")
    NODES_FIELD_NUMBER: _ClassVar[int]
    CONVO_INFO_FIELD_NUMBER: _ClassVar[int]
    THREADS_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.RepeatedCompositeFieldContainer[ConvoNode]
    convo_info: ConvoInfo
    threads: _containers.RepeatedCompositeFieldContainer[ConvoThreadInfo]
    def __init__(self, nodes: _Optional[_Iterable[_Union[ConvoNode, _Mapping]]] = ..., convo_info: _Optional[_Union[ConvoInfo, _Mapping]] = ..., threads: _Optional[_Iterable[_Union[ConvoThreadInfo, _Mapping]]] = ...) -> None: ...

class ConvoStreamUpdate(_message.Message):
    __slots__ = ("nodes", "threads", "convo_info", "error", "agent_updates")
    class ConvoAgentBlockUpdate(_message.Message):
        __slots__ = ("node_id", "block_id", "streaming_reply_content", "streaming_thought_content")
        NODE_ID_FIELD_NUMBER: _ClassVar[int]
        BLOCK_ID_FIELD_NUMBER: _ClassVar[int]
        STREAMING_REPLY_CONTENT_FIELD_NUMBER: _ClassVar[int]
        STREAMING_THOUGHT_CONTENT_FIELD_NUMBER: _ClassVar[int]
        node_id: int
        block_id: int
        streaming_reply_content: str
        streaming_thought_content: str
        def __init__(self, node_id: _Optional[int] = ..., block_id: _Optional[int] = ..., streaming_reply_content: _Optional[str] = ..., streaming_thought_content: _Optional[str] = ...) -> None: ...
    NODES_FIELD_NUMBER: _ClassVar[int]
    THREADS_FIELD_NUMBER: _ClassVar[int]
    CONVO_INFO_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    AGENT_UPDATES_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.RepeatedCompositeFieldContainer[ConvoNode]
    threads: _containers.RepeatedCompositeFieldContainer[ConvoThreadInfo]
    convo_info: ConvoInfo
    error: ConvoErrorBlock
    agent_updates: _containers.RepeatedCompositeFieldContainer[ConvoStreamUpdate.ConvoAgentBlockUpdate]
    def __init__(self, nodes: _Optional[_Iterable[_Union[ConvoNode, _Mapping]]] = ..., threads: _Optional[_Iterable[_Union[ConvoThreadInfo, _Mapping]]] = ..., convo_info: _Optional[_Union[ConvoInfo, _Mapping]] = ..., error: _Optional[_Union[ConvoErrorBlock, _Mapping]] = ..., agent_updates: _Optional[_Iterable[_Union[ConvoStreamUpdate.ConvoAgentBlockUpdate, _Mapping]]] = ...) -> None: ...

class ConvoOpenStreamRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetConvoNodesRequest(_message.Message):
    __slots__ = ("thread_id", "target_node_id", "max_before", "max_after")
    THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    TARGET_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    MAX_BEFORE_FIELD_NUMBER: _ClassVar[int]
    MAX_AFTER_FIELD_NUMBER: _ClassVar[int]
    thread_id: int
    target_node_id: int
    max_before: int
    max_after: int
    def __init__(self, thread_id: _Optional[int] = ..., target_node_id: _Optional[int] = ..., max_before: _Optional[int] = ..., max_after: _Optional[int] = ...) -> None: ...

class GetConvoNodesResponse(_message.Message):
    __slots__ = ("nodes", "convo_info")
    NODES_FIELD_NUMBER: _ClassVar[int]
    CONVO_INFO_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.RepeatedCompositeFieldContainer[ConvoNode]
    convo_info: ConvoInfo
    def __init__(self, nodes: _Optional[_Iterable[_Union[ConvoNode, _Mapping]]] = ..., convo_info: _Optional[_Union[ConvoInfo, _Mapping]] = ...) -> None: ...

class GetConvoThreadsRequest(_message.Message):
    __slots__ = ("include_system_threads", "include_latest_nodes", "include_anchor_nodes")
    INCLUDE_SYSTEM_THREADS_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_LATEST_NODES_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_ANCHOR_NODES_FIELD_NUMBER: _ClassVar[int]
    include_system_threads: bool
    include_latest_nodes: bool
    include_anchor_nodes: bool
    def __init__(self, include_system_threads: bool = ..., include_latest_nodes: bool = ..., include_anchor_nodes: bool = ...) -> None: ...

class GetConvoThreadsResponse(_message.Message):
    __slots__ = ("threads", "convo_info")
    THREADS_FIELD_NUMBER: _ClassVar[int]
    CONVO_INFO_FIELD_NUMBER: _ClassVar[int]
    threads: _containers.RepeatedCompositeFieldContainer[ConvoThreadInfo]
    convo_info: ConvoInfo
    def __init__(self, threads: _Optional[_Iterable[_Union[ConvoThreadInfo, _Mapping]]] = ..., convo_info: _Optional[_Union[ConvoInfo, _Mapping]] = ...) -> None: ...

class MarkConvoThreadReadRequest(_message.Message):
    __slots__ = ("thread_id", "through_node_id")
    THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    THROUGH_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    thread_id: int
    through_node_id: int
    def __init__(self, thread_id: _Optional[int] = ..., through_node_id: _Optional[int] = ...) -> None: ...

class MarkConvoThreadReadResponse(_message.Message):
    __slots__ = ("thread", "convo_info")
    THREAD_FIELD_NUMBER: _ClassVar[int]
    CONVO_INFO_FIELD_NUMBER: _ClassVar[int]
    thread: ConvoThreadInfo
    convo_info: ConvoInfo
    def __init__(self, thread: _Optional[_Union[ConvoThreadInfo, _Mapping]] = ..., convo_info: _Optional[_Union[ConvoInfo, _Mapping]] = ...) -> None: ...

class RenameConvoThreadRequest(_message.Message):
    __slots__ = ("thread_id", "display_name")
    THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    DISPLAY_NAME_FIELD_NUMBER: _ClassVar[int]
    thread_id: int
    display_name: str
    def __init__(self, thread_id: _Optional[int] = ..., display_name: _Optional[str] = ...) -> None: ...

class RenameConvoThreadResponse(_message.Message):
    __slots__ = ("thread", "convo_info")
    THREAD_FIELD_NUMBER: _ClassVar[int]
    CONVO_INFO_FIELD_NUMBER: _ClassVar[int]
    thread: ConvoThreadInfo
    convo_info: ConvoInfo
    def __init__(self, thread: _Optional[_Union[ConvoThreadInfo, _Mapping]] = ..., convo_info: _Optional[_Union[ConvoInfo, _Mapping]] = ...) -> None: ...

class ConvoUserResponseRequest(_message.Message):
    __slots__ = ("target_thread_id", "user", "attachments", "agent_should_respond_in_subthread")
    TARGET_THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    ATTACHMENTS_FIELD_NUMBER: _ClassVar[int]
    AGENT_SHOULD_RESPOND_IN_SUBTHREAD_FIELD_NUMBER: _ClassVar[int]
    target_thread_id: int
    user: ConvoUserBlock
    attachments: ConvoNodeAttachments
    agent_should_respond_in_subthread: bool
    def __init__(self, target_thread_id: _Optional[int] = ..., user: _Optional[_Union[ConvoUserBlock, _Mapping]] = ..., attachments: _Optional[_Union[ConvoNodeAttachments, _Mapping]] = ..., agent_should_respond_in_subthread: bool = ...) -> None: ...

class ConvoUserResponseResponse(_message.Message):
    __slots__ = ("node", "convo_info")
    NODE_FIELD_NUMBER: _ClassVar[int]
    CONVO_INFO_FIELD_NUMBER: _ClassVar[int]
    node: ConvoNode
    convo_info: ConvoInfo
    def __init__(self, node: _Optional[_Union[ConvoNode, _Mapping]] = ..., convo_info: _Optional[_Union[ConvoInfo, _Mapping]] = ...) -> None: ...

class ConvoResetRequest(_message.Message):
    __slots__ = ("hard_reset",)
    HARD_RESET_FIELD_NUMBER: _ClassVar[int]
    hard_reset: bool
    def __init__(self, hard_reset: bool = ...) -> None: ...

class ConvoResetResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ConvoSearchRequest(_message.Message):
    __slots__ = ("query", "max_results", "offset")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    MAX_RESULTS_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    query: str
    max_results: int
    offset: int
    def __init__(self, query: _Optional[str] = ..., max_results: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ConvoSearchResponse(_message.Message):
    __slots__ = ("results",)
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[ConvoNode]
    def __init__(self, results: _Optional[_Iterable[_Union[ConvoNode, _Mapping]]] = ...) -> None: ...

class ConvoForwardBlock(_message.Message):
    __slots__ = ("forwarded_node_id", "forwarded_thread_id", "source_label", "user_response")
    FORWARDED_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    FORWARDED_THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_LABEL_FIELD_NUMBER: _ClassVar[int]
    USER_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    forwarded_node_id: int
    forwarded_thread_id: int
    source_label: str
    user_response: ConvoUserBlock
    def __init__(self, forwarded_node_id: _Optional[int] = ..., forwarded_thread_id: _Optional[int] = ..., source_label: _Optional[str] = ..., user_response: _Optional[_Union[ConvoUserBlock, _Mapping]] = ...) -> None: ...

class ConvoForwardRequest(_message.Message):
    __slots__ = ("user_response", "forwarded_node_id", "forwarded_thread_id", "source_label")
    USER_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    FORWARDED_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    FORWARDED_THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_LABEL_FIELD_NUMBER: _ClassVar[int]
    user_response: ConvoUserResponseRequest
    forwarded_node_id: int
    forwarded_thread_id: int
    source_label: str
    def __init__(self, user_response: _Optional[_Union[ConvoUserResponseRequest, _Mapping]] = ..., forwarded_node_id: _Optional[int] = ..., forwarded_thread_id: _Optional[int] = ..., source_label: _Optional[str] = ...) -> None: ...

class ConvoForwardResponse(_message.Message):
    __slots__ = ("node", "convo_info")
    NODE_FIELD_NUMBER: _ClassVar[int]
    CONVO_INFO_FIELD_NUMBER: _ClassVar[int]
    node: ConvoNode
    convo_info: ConvoInfo
    def __init__(self, node: _Optional[_Union[ConvoNode, _Mapping]] = ..., convo_info: _Optional[_Union[ConvoInfo, _Mapping]] = ...) -> None: ...

class ConvoResolveActionRequest(_message.Message):
    __slots__ = ("action_node_id", "status", "response_text")
    ACTION_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_TEXT_FIELD_NUMBER: _ClassVar[int]
    action_node_id: int
    status: ConvoActionBlock.Status
    response_text: str
    def __init__(self, action_node_id: _Optional[int] = ..., status: _Optional[_Union[ConvoActionBlock.Status, str]] = ..., response_text: _Optional[str] = ...) -> None: ...

class ConvoResolveActionResponse(_message.Message):
    __slots__ = ("node", "convo_info")
    NODE_FIELD_NUMBER: _ClassVar[int]
    CONVO_INFO_FIELD_NUMBER: _ClassVar[int]
    node: ConvoNode
    convo_info: ConvoInfo
    def __init__(self, node: _Optional[_Union[ConvoNode, _Mapping]] = ..., convo_info: _Optional[_Union[ConvoInfo, _Mapping]] = ...) -> None: ...

class ConvoInterruptRequest(_message.Message):
    __slots__ = ("target_thread_id",)
    TARGET_THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    target_thread_id: int
    def __init__(self, target_thread_id: _Optional[int] = ...) -> None: ...

class ConvoInterruptResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
