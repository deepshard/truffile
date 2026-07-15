import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from truffle.common import schedule_pb2 as _schedule_pb2
from truffle.os import convo_pb2 as _convo_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class BgAgentSchedule(_message.Message):
    __slots__ = ("schedule_id", "description", "prompt", "enabled", "schedule", "next_run_at", "last_run_at", "last_run_ref")
    SCHEDULE_ID_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    PROMPT_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    SCHEDULE_FIELD_NUMBER: _ClassVar[int]
    NEXT_RUN_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_RUN_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_RUN_REF_FIELD_NUMBER: _ClassVar[int]
    schedule_id: str
    description: str
    prompt: str
    enabled: bool
    schedule: _schedule_pb2.SchedulePolicy
    next_run_at: _timestamp_pb2.Timestamp
    last_run_at: _timestamp_pb2.Timestamp
    last_run_ref: _convo_pb2.ConvoNodeRef
    def __init__(self, schedule_id: _Optional[str] = ..., description: _Optional[str] = ..., prompt: _Optional[str] = ..., enabled: bool = ..., schedule: _Optional[_Union[_schedule_pb2.SchedulePolicy, _Mapping]] = ..., next_run_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., last_run_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., last_run_ref: _Optional[_Union[_convo_pb2.ConvoNodeRef, _Mapping]] = ...) -> None: ...

class ListBgAgentSchedulesRequest(_message.Message):
    __slots__ = ("limit", "offset")
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    limit: int
    offset: int
    def __init__(self, limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ListBgAgentSchedulesResponse(_message.Message):
    __slots__ = ("schedules",)
    SCHEDULES_FIELD_NUMBER: _ClassVar[int]
    schedules: _containers.RepeatedCompositeFieldContainer[BgAgentSchedule]
    def __init__(self, schedules: _Optional[_Iterable[_Union[BgAgentSchedule, _Mapping]]] = ...) -> None: ...

class UpsertBgAgentScheduleRequest(_message.Message):
    __slots__ = ("schedule",)
    SCHEDULE_FIELD_NUMBER: _ClassVar[int]
    schedule: BgAgentSchedule
    def __init__(self, schedule: _Optional[_Union[BgAgentSchedule, _Mapping]] = ...) -> None: ...

class UpsertBgAgentScheduleResponse(_message.Message):
    __slots__ = ("schedule",)
    SCHEDULE_FIELD_NUMBER: _ClassVar[int]
    schedule: BgAgentSchedule
    def __init__(self, schedule: _Optional[_Union[BgAgentSchedule, _Mapping]] = ...) -> None: ...

class DeleteBgAgentScheduleRequest(_message.Message):
    __slots__ = ("schedule_id",)
    SCHEDULE_ID_FIELD_NUMBER: _ClassVar[int]
    schedule_id: str
    def __init__(self, schedule_id: _Optional[str] = ...) -> None: ...

class DeleteBgAgentScheduleResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class BgAgentScheduleRunNowRequest(_message.Message):
    __slots__ = ("schedule_id",)
    SCHEDULE_ID_FIELD_NUMBER: _ClassVar[int]
    schedule_id: str
    def __init__(self, schedule_id: _Optional[str] = ...) -> None: ...

class BgAgentScheduleRunNowResponse(_message.Message):
    __slots__ = ("schedule",)
    SCHEDULE_FIELD_NUMBER: _ClassVar[int]
    schedule: BgAgentSchedule
    def __init__(self, schedule: _Optional[_Union[BgAgentSchedule, _Mapping]] = ...) -> None: ...

class BgAgentExternalContext(_message.Message):
    __slots__ = ("source_id", "source_title", "content", "extra", "coalesce_policy")
    class ExternalContextCoalescePolicy(_message.Message):
        __slots__ = ("coalesce_window", "coalesce_cap", "immediate")
        COALESCE_WINDOW_FIELD_NUMBER: _ClassVar[int]
        COALESCE_CAP_FIELD_NUMBER: _ClassVar[int]
        IMMEDIATE_FIELD_NUMBER: _ClassVar[int]
        coalesce_window: _duration_pb2.Duration
        coalesce_cap: int
        immediate: bool
        def __init__(self, coalesce_window: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., coalesce_cap: _Optional[int] = ..., immediate: bool = ...) -> None: ...
    SOURCE_ID_FIELD_NUMBER: _ClassVar[int]
    SOURCE_TITLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    EXTRA_FIELD_NUMBER: _ClassVar[int]
    COALESCE_POLICY_FIELD_NUMBER: _ClassVar[int]
    source_id: str
    source_title: str
    content: str
    extra: _struct_pb2.Struct
    coalesce_policy: BgAgentExternalContext.ExternalContextCoalescePolicy
    def __init__(self, source_id: _Optional[str] = ..., source_title: _Optional[str] = ..., content: _Optional[str] = ..., extra: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., coalesce_policy: _Optional[_Union[BgAgentExternalContext.ExternalContextCoalescePolicy, _Mapping]] = ...) -> None: ...

class BgAgentSubmitExternalContextRequest(_message.Message):
    __slots__ = ("context",)
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    context: BgAgentExternalContext
    def __init__(self, context: _Optional[_Union[BgAgentExternalContext, _Mapping]] = ...) -> None: ...

class BgAgentSubmitExternalContextResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
