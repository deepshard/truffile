import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from truffle.common import schedule_pb2 as _schedule_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DreamModeSettings(_message.Message):
    __slots__ = ("enabled", "inactivity_timeout", "schedule")
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    INACTIVITY_TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    SCHEDULE_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    inactivity_timeout: _duration_pb2.Duration
    schedule: _schedule_pb2.Schedule
    def __init__(self, enabled: bool = ..., inactivity_timeout: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., schedule: _Optional[_Union[_schedule_pb2.Schedule, _Mapping]] = ...) -> None: ...

class DreamModeStatus(_message.Message):
    __slots__ = ("enabled", "active_run", "will_run_next_window", "progress_until_dream_eligible")
    class ActiveDreamRunInfo(_message.Message):
        __slots__ = ("run_id", "model_id", "started_at", "status", "progress", "events")
        class DreamRunEvent(_message.Message):
            __slots__ = ("event_id", "created_at", "status", "stats", "extra", "error_message", "eta", "last_step_duration")
            EVENT_ID_FIELD_NUMBER: _ClassVar[int]
            CREATED_AT_FIELD_NUMBER: _ClassVar[int]
            STATUS_FIELD_NUMBER: _ClassVar[int]
            STATS_FIELD_NUMBER: _ClassVar[int]
            EXTRA_FIELD_NUMBER: _ClassVar[int]
            ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
            ETA_FIELD_NUMBER: _ClassVar[int]
            LAST_STEP_DURATION_FIELD_NUMBER: _ClassVar[int]
            event_id: str
            created_at: _timestamp_pb2.Timestamp
            status: str
            stats: _struct_pb2.Struct
            extra: _struct_pb2.Struct
            error_message: str
            eta: _duration_pb2.Duration
            last_step_duration: _duration_pb2.Duration
            def __init__(self, event_id: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., status: _Optional[str] = ..., stats: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., extra: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., error_message: _Optional[str] = ..., eta: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., last_step_duration: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ...) -> None: ...
        RUN_ID_FIELD_NUMBER: _ClassVar[int]
        MODEL_ID_FIELD_NUMBER: _ClassVar[int]
        STARTED_AT_FIELD_NUMBER: _ClassVar[int]
        STATUS_FIELD_NUMBER: _ClassVar[int]
        PROGRESS_FIELD_NUMBER: _ClassVar[int]
        EVENTS_FIELD_NUMBER: _ClassVar[int]
        run_id: str
        model_id: str
        started_at: _timestamp_pb2.Timestamp
        status: str
        progress: float
        events: _containers.RepeatedCompositeFieldContainer[DreamModeStatus.ActiveDreamRunInfo.DreamRunEvent]
        def __init__(self, run_id: _Optional[str] = ..., model_id: _Optional[str] = ..., started_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., status: _Optional[str] = ..., progress: _Optional[float] = ..., events: _Optional[_Iterable[_Union[DreamModeStatus.ActiveDreamRunInfo.DreamRunEvent, _Mapping]]] = ...) -> None: ...
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_RUN_FIELD_NUMBER: _ClassVar[int]
    WILL_RUN_NEXT_WINDOW_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_UNTIL_DREAM_ELIGIBLE_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    active_run: DreamModeStatus.ActiveDreamRunInfo
    will_run_next_window: bool
    progress_until_dream_eligible: int
    def __init__(self, enabled: bool = ..., active_run: _Optional[_Union[DreamModeStatus.ActiveDreamRunInfo, _Mapping]] = ..., will_run_next_window: bool = ..., progress_until_dream_eligible: _Optional[int] = ...) -> None: ...

class GetDreamModeStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetDreamModeStatusResponse(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: DreamModeStatus
    def __init__(self, status: _Optional[_Union[DreamModeStatus, _Mapping]] = ...) -> None: ...
