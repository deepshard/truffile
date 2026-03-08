import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf import descriptor_pb2 as _descriptor_pb2
from truffle.common import icon_pb2 as _icon_pb2
from truffle.app import app_build_pb2 as _app_build_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class BackgroundAppRuntimePolicy(_message.Message):
    __slots__ = ("interval", "times", "always", "feed_entry_retention")
    class TimeOfDay(_message.Message):
        __slots__ = ("hour", "minute", "second")
        HOUR_FIELD_NUMBER: _ClassVar[int]
        MINUTE_FIELD_NUMBER: _ClassVar[int]
        SECOND_FIELD_NUMBER: _ClassVar[int]
        hour: int
        minute: int
        second: int
        def __init__(self, hour: _Optional[int] = ..., minute: _Optional[int] = ..., second: _Optional[int] = ...) -> None: ...
    class DailyWindow(_message.Message):
        __slots__ = ("daily_start_time", "daily_end_time")
        DAILY_START_TIME_FIELD_NUMBER: _ClassVar[int]
        DAILY_END_TIME_FIELD_NUMBER: _ClassVar[int]
        daily_start_time: BackgroundAppRuntimePolicy.TimeOfDay
        daily_end_time: BackgroundAppRuntimePolicy.TimeOfDay
        def __init__(self, daily_start_time: _Optional[_Union[BackgroundAppRuntimePolicy.TimeOfDay, _Mapping]] = ..., daily_end_time: _Optional[_Union[BackgroundAppRuntimePolicy.TimeOfDay, _Mapping]] = ...) -> None: ...
    class WeeklyWindow(_message.Message):
        __slots__ = ("day_mask",)
        class Masks(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
            __slots__ = ()
            WEEKLY_WINDOW_DEFAULT: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_ALL_DAYS: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_SATURDAY: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_FRIDAY: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_THURSDAY: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_WEDNESDAY: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_TUESDAY: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_MONDAY: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_SUNDAY: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_WEEKENDS: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_WEEKDAYS: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_NO_DAYS: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
            WEEKLY_WINDOW_INVALID: _ClassVar[BackgroundAppRuntimePolicy.WeeklyWindow.Masks]
        WEEKLY_WINDOW_DEFAULT: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_ALL_DAYS: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_SATURDAY: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_FRIDAY: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_THURSDAY: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_WEDNESDAY: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_TUESDAY: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_MONDAY: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_SUNDAY: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_WEEKENDS: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_WEEKDAYS: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_NO_DAYS: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        WEEKLY_WINDOW_INVALID: BackgroundAppRuntimePolicy.WeeklyWindow.Masks
        DAY_MASK_FIELD_NUMBER: _ClassVar[int]
        day_mask: int
        def __init__(self, day_mask: _Optional[int] = ...) -> None: ...
    class Interval(_message.Message):
        __slots__ = ("duration", "schedule")
        class Schedule(_message.Message):
            __slots__ = ("daily_window", "weekly_window")
            DAILY_WINDOW_FIELD_NUMBER: _ClassVar[int]
            WEEKLY_WINDOW_FIELD_NUMBER: _ClassVar[int]
            daily_window: BackgroundAppRuntimePolicy.DailyWindow
            weekly_window: BackgroundAppRuntimePolicy.WeeklyWindow
            def __init__(self, daily_window: _Optional[_Union[BackgroundAppRuntimePolicy.DailyWindow, _Mapping]] = ..., weekly_window: _Optional[_Union[BackgroundAppRuntimePolicy.WeeklyWindow, _Mapping]] = ...) -> None: ...
        DURATION_FIELD_NUMBER: _ClassVar[int]
        SCHEDULE_FIELD_NUMBER: _ClassVar[int]
        duration: _duration_pb2.Duration
        schedule: BackgroundAppRuntimePolicy.Interval.Schedule
        def __init__(self, duration: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., schedule: _Optional[_Union[BackgroundAppRuntimePolicy.Interval.Schedule, _Mapping]] = ...) -> None: ...
    class SpecificTimes(_message.Message):
        __slots__ = ("run_times", "weekly_window")
        RUN_TIMES_FIELD_NUMBER: _ClassVar[int]
        WEEKLY_WINDOW_FIELD_NUMBER: _ClassVar[int]
        run_times: _containers.RepeatedCompositeFieldContainer[BackgroundAppRuntimePolicy.TimeOfDay]
        weekly_window: BackgroundAppRuntimePolicy.WeeklyWindow
        def __init__(self, run_times: _Optional[_Iterable[_Union[BackgroundAppRuntimePolicy.TimeOfDay, _Mapping]]] = ..., weekly_window: _Optional[_Union[BackgroundAppRuntimePolicy.WeeklyWindow, _Mapping]] = ...) -> None: ...
    class Always(_message.Message):
        __slots__ = ()
        def __init__(self) -> None: ...
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    TIMES_FIELD_NUMBER: _ClassVar[int]
    ALWAYS_FIELD_NUMBER: _ClassVar[int]
    FEED_ENTRY_RETENTION_FIELD_NUMBER: _ClassVar[int]
    interval: BackgroundAppRuntimePolicy.Interval
    times: BackgroundAppRuntimePolicy.SpecificTimes
    always: BackgroundAppRuntimePolicy.Always
    feed_entry_retention: _duration_pb2.Duration
    def __init__(self, interval: _Optional[_Union[BackgroundAppRuntimePolicy.Interval, _Mapping]] = ..., times: _Optional[_Union[BackgroundAppRuntimePolicy.SpecificTimes, _Mapping]] = ..., always: _Optional[_Union[BackgroundAppRuntimePolicy.Always, _Mapping]] = ..., feed_entry_retention: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ...) -> None: ...

class BackgroundApp(_message.Message):
    __slots__ = ("runtime_policy",)
    RUNTIME_POLICY_FIELD_NUMBER: _ClassVar[int]
    runtime_policy: BackgroundAppRuntimePolicy
    def __init__(self, runtime_policy: _Optional[_Union[BackgroundAppRuntimePolicy, _Mapping]] = ...) -> None: ...

class BackgroundAppBuildInfo(_message.Message):
    __slots__ = ("process", "runtime_policy")
    PROCESS_FIELD_NUMBER: _ClassVar[int]
    RUNTIME_POLICY_FIELD_NUMBER: _ClassVar[int]
    process: _app_build_pb2.ProcessConfig
    runtime_policy: BackgroundAppRuntimePolicy
    def __init__(self, process: _Optional[_Union[_app_build_pb2.ProcessConfig, _Mapping]] = ..., runtime_policy: _Optional[_Union[BackgroundAppRuntimePolicy, _Mapping]] = ...) -> None: ...

class BackgroundContext(_message.Message):
    __slots__ = ("content", "uris", "priority")
    class Priority(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        PRIORITY_UNSPECIFIED: _ClassVar[BackgroundContext.Priority]
        PRIORITY_LOW: _ClassVar[BackgroundContext.Priority]
        PRIORITY_HIGH: _ClassVar[BackgroundContext.Priority]
    PRIORITY_UNSPECIFIED: BackgroundContext.Priority
    PRIORITY_LOW: BackgroundContext.Priority
    PRIORITY_HIGH: BackgroundContext.Priority
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    URIS_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    content: str
    uris: _containers.RepeatedScalarFieldContainer[str]
    priority: BackgroundContext.Priority
    def __init__(self, content: _Optional[str] = ..., uris: _Optional[_Iterable[str]] = ..., priority: _Optional[_Union[BackgroundContext.Priority, str]] = ...) -> None: ...

class BackgroundAppSubmitContextRequest(_message.Message):
    __slots__ = ("content",)
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    content: BackgroundContext
    def __init__(self, content: _Optional[_Union[BackgroundContext, _Mapping]] = ...) -> None: ...

class BackgroundAppSubmitContextResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class BackgroundAppOnRunRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class BackgroundAppOnRunResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class BackgroundAppYieldRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class BackgroundAppYieldResponse(_message.Message):
    __slots__ = ("next_scheduled_run_time",)
    NEXT_SCHEDULED_RUN_TIME_FIELD_NUMBER: _ClassVar[int]
    next_scheduled_run_time: _timestamp_pb2.Timestamp
    def __init__(self, next_scheduled_run_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class BackgroundAppReportErrorResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
