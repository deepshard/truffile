import datetime

from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

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
    daily_start_time: TimeOfDay
    daily_end_time: TimeOfDay
    def __init__(self, daily_start_time: _Optional[_Union[TimeOfDay, _Mapping]] = ..., daily_end_time: _Optional[_Union[TimeOfDay, _Mapping]] = ...) -> None: ...

class WeeklyWindow(_message.Message):
    __slots__ = ("day_mask",)
    class Masks(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        WEEKLY_WINDOW_DEFAULT: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_ALL_DAYS: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_SATURDAY: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_FRIDAY: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_THURSDAY: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_WEDNESDAY: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_TUESDAY: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_MONDAY: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_SUNDAY: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_WEEKENDS: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_WEEKDAYS: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_NO_DAYS: _ClassVar[WeeklyWindow.Masks]
        WEEKLY_WINDOW_INVALID: _ClassVar[WeeklyWindow.Masks]
    WEEKLY_WINDOW_DEFAULT: WeeklyWindow.Masks
    WEEKLY_WINDOW_ALL_DAYS: WeeklyWindow.Masks
    WEEKLY_WINDOW_SATURDAY: WeeklyWindow.Masks
    WEEKLY_WINDOW_FRIDAY: WeeklyWindow.Masks
    WEEKLY_WINDOW_THURSDAY: WeeklyWindow.Masks
    WEEKLY_WINDOW_WEDNESDAY: WeeklyWindow.Masks
    WEEKLY_WINDOW_TUESDAY: WeeklyWindow.Masks
    WEEKLY_WINDOW_MONDAY: WeeklyWindow.Masks
    WEEKLY_WINDOW_SUNDAY: WeeklyWindow.Masks
    WEEKLY_WINDOW_WEEKENDS: WeeklyWindow.Masks
    WEEKLY_WINDOW_WEEKDAYS: WeeklyWindow.Masks
    WEEKLY_WINDOW_NO_DAYS: WeeklyWindow.Masks
    WEEKLY_WINDOW_INVALID: WeeklyWindow.Masks
    DAY_MASK_FIELD_NUMBER: _ClassVar[int]
    day_mask: int
    def __init__(self, day_mask: _Optional[int] = ...) -> None: ...

class Schedule(_message.Message):
    __slots__ = ("daily_window", "weekly_window")
    DAILY_WINDOW_FIELD_NUMBER: _ClassVar[int]
    WEEKLY_WINDOW_FIELD_NUMBER: _ClassVar[int]
    daily_window: DailyWindow
    weekly_window: WeeklyWindow
    def __init__(self, daily_window: _Optional[_Union[DailyWindow, _Mapping]] = ..., weekly_window: _Optional[_Union[WeeklyWindow, _Mapping]] = ...) -> None: ...

class IntervalSchedule(_message.Message):
    __slots__ = ("duration", "schedule")
    DURATION_FIELD_NUMBER: _ClassVar[int]
    SCHEDULE_FIELD_NUMBER: _ClassVar[int]
    duration: _duration_pb2.Duration
    schedule: Schedule
    def __init__(self, duration: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., schedule: _Optional[_Union[Schedule, _Mapping]] = ...) -> None: ...

class SpecificTimesSchedule(_message.Message):
    __slots__ = ("run_times", "weekly_window")
    RUN_TIMES_FIELD_NUMBER: _ClassVar[int]
    WEEKLY_WINDOW_FIELD_NUMBER: _ClassVar[int]
    run_times: _containers.RepeatedCompositeFieldContainer[TimeOfDay]
    weekly_window: WeeklyWindow
    def __init__(self, run_times: _Optional[_Iterable[_Union[TimeOfDay, _Mapping]]] = ..., weekly_window: _Optional[_Union[WeeklyWindow, _Mapping]] = ...) -> None: ...

class AlwaysSchedule(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SchedulePolicy(_message.Message):
    __slots__ = ("interval", "times")
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    TIMES_FIELD_NUMBER: _ClassVar[int]
    interval: IntervalSchedule
    times: SpecificTimesSchedule
    def __init__(self, interval: _Optional[_Union[IntervalSchedule, _Mapping]] = ..., times: _Optional[_Union[SpecificTimesSchedule, _Mapping]] = ...) -> None: ...

class RunSchedulePolicy(_message.Message):
    __slots__ = ("interval", "times", "always")
    INTERVAL_FIELD_NUMBER: _ClassVar[int]
    TIMES_FIELD_NUMBER: _ClassVar[int]
    ALWAYS_FIELD_NUMBER: _ClassVar[int]
    interval: IntervalSchedule
    times: SpecificTimesSchedule
    always: AlwaysSchedule
    def __init__(self, interval: _Optional[_Union[IntervalSchedule, _Mapping]] = ..., times: _Optional[_Union[SpecificTimesSchedule, _Mapping]] = ..., always: _Optional[_Union[AlwaysSchedule, _Mapping]] = ...) -> None: ...
