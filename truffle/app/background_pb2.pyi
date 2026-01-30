from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf import descriptor_pb2 as _descriptor_pb2
from truffle.app import background_feed_pb2 as _background_feed_pb2
from truffle.common import icon_pb2 as _icon_pb2
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
        def __init__(self, duration: _Optional[_Union[_duration_pb2.Duration, _Mapping]] = ..., schedule: _Optional[_Union[BackgroundAppRuntimePolicy.Interval.Schedule, _Mapping]] = ...) -> None: ...
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
    def __init__(self, interval: _Optional[_Union[BackgroundAppRuntimePolicy.Interval, _Mapping]] = ..., times: _Optional[_Union[BackgroundAppRuntimePolicy.SpecificTimes, _Mapping]] = ..., always: _Optional[_Union[BackgroundAppRuntimePolicy.Always, _Mapping]] = ..., feed_entry_retention: _Optional[_Union[_duration_pb2.Duration, _Mapping]] = ...) -> None: ...

class BackgroundApp(_message.Message):
    __slots__ = ("uuid", "metadata", "runtime_policy")
    class Metadata(_message.Message):
        __slots__ = ("name", "icon", "description")
        NAME_FIELD_NUMBER: _ClassVar[int]
        ICON_FIELD_NUMBER: _ClassVar[int]
        DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
        name: str
        icon: _icon_pb2.Icon
        description: str
        def __init__(self, name: _Optional[str] = ..., icon: _Optional[_Union[_icon_pb2.Icon, _Mapping]] = ..., description: _Optional[str] = ...) -> None: ...
    UUID_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    RUNTIME_POLICY_FIELD_NUMBER: _ClassVar[int]
    uuid: str
    metadata: BackgroundApp.Metadata
    runtime_policy: BackgroundAppRuntimePolicy
    def __init__(self, uuid: _Optional[str] = ..., metadata: _Optional[_Union[BackgroundApp.Metadata, _Mapping]] = ..., runtime_policy: _Optional[_Union[BackgroundAppRuntimePolicy, _Mapping]] = ...) -> None: ...

class BackgroundAppNotification(_message.Message):
    __slots__ = ("feed_entry_ids", "operation")
    class Operation(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        OPERATION_INVALID: _ClassVar[BackgroundAppNotification.Operation]
        OPERATION_ADD: _ClassVar[BackgroundAppNotification.Operation]
        OPERATION_DELETE: _ClassVar[BackgroundAppNotification.Operation]
        OPERATION_REFRESH: _ClassVar[BackgroundAppNotification.Operation]
    OPERATION_INVALID: BackgroundAppNotification.Operation
    OPERATION_ADD: BackgroundAppNotification.Operation
    OPERATION_DELETE: BackgroundAppNotification.Operation
    OPERATION_REFRESH: BackgroundAppNotification.Operation
    FEED_ENTRY_IDS_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    feed_entry_ids: _containers.RepeatedScalarFieldContainer[int]
    operation: BackgroundAppNotification.Operation
    def __init__(self, feed_entry_ids: _Optional[_Iterable[int]] = ..., operation: _Optional[_Union[BackgroundAppNotification.Operation, str]] = ...) -> None: ...

class BackgroundAppBuildInfo(_message.Message):
    __slots__ = ("metadata", "runtime_policy")
    METADATA_FIELD_NUMBER: _ClassVar[int]
    RUNTIME_POLICY_FIELD_NUMBER: _ClassVar[int]
    metadata: BackgroundApp.Metadata
    runtime_policy: BackgroundAppRuntimePolicy
    def __init__(self, metadata: _Optional[_Union[BackgroundApp.Metadata, _Mapping]] = ..., runtime_policy: _Optional[_Union[BackgroundAppRuntimePolicy, _Mapping]] = ...) -> None: ...

class BackgroundAppSubmitFeedContentRequest(_message.Message):
    __slots__ = ("card",)
    CARD_FIELD_NUMBER: _ClassVar[int]
    card: _background_feed_pb2.FeedCard
    def __init__(self, card: _Optional[_Union[_background_feed_pb2.FeedCard, _Mapping]] = ...) -> None: ...

class BackgroundAppSubmitFeedContentResponse(_message.Message):
    __slots__ = ("feed_entry_id",)
    FEED_ENTRY_ID_FIELD_NUMBER: _ClassVar[int]
    feed_entry_id: int
    def __init__(self, feed_entry_id: _Optional[int] = ...) -> None: ...

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
    def __init__(self, next_scheduled_run_time: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class BackgroundAppError(_message.Message):
    __slots__ = ("error_type", "error_message")
    class ErrorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        BG_APP_ERROR_TYPE_INVALID: _ClassVar[BackgroundAppError.ErrorType]
        BG_APP_ERROR_TYPE_RUNTIME: _ClassVar[BackgroundAppError.ErrorType]
        BG_APP_ERROR_AUTH: _ClassVar[BackgroundAppError.ErrorType]
        BG_APP_ERROR_TYPE_UNKNOWN: _ClassVar[BackgroundAppError.ErrorType]
    BG_APP_ERROR_TYPE_INVALID: BackgroundAppError.ErrorType
    BG_APP_ERROR_TYPE_RUNTIME: BackgroundAppError.ErrorType
    BG_APP_ERROR_AUTH: BackgroundAppError.ErrorType
    BG_APP_ERROR_TYPE_UNKNOWN: BackgroundAppError.ErrorType
    ERROR_TYPE_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    error_type: BackgroundAppError.ErrorType
    error_message: str
    def __init__(self, error_type: _Optional[_Union[BackgroundAppError.ErrorType, str]] = ..., error_message: _Optional[str] = ...) -> None: ...

class BackgroundAppReportErrorRequest(_message.Message):
    __slots__ = ("error", "needs_intervention")
    ERROR_FIELD_NUMBER: _ClassVar[int]
    NEEDS_INTERVENTION_FIELD_NUMBER: _ClassVar[int]
    error: BackgroundAppError
    needs_intervention: bool
    def __init__(self, error: _Optional[_Union[BackgroundAppError, _Mapping]] = ..., needs_intervention: bool = ...) -> None: ...

class BackgroundAppReportErrorResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
