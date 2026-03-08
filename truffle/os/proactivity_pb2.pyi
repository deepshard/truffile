import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ProactiveAction(_message.Message):
    __slots__ = ("title", "description", "actionable", "status", "created_at", "updated_at", "app_uuids", "prompt_for_subagent")
    class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        ACTION_STATE_INVALID: _ClassVar[ProactiveAction.Status]
        ACTION_STATE_PENDING: _ClassVar[ProactiveAction.Status]
        ACTION_STATE_IN_PROGRESS: _ClassVar[ProactiveAction.Status]
        ACTION_STATE_CANCELLED: _ClassVar[ProactiveAction.Status]
        ACTION_STATE_COMPLETED: _ClassVar[ProactiveAction.Status]
    ACTION_STATE_INVALID: ProactiveAction.Status
    ACTION_STATE_PENDING: ProactiveAction.Status
    ACTION_STATE_IN_PROGRESS: ProactiveAction.Status
    ACTION_STATE_CANCELLED: ProactiveAction.Status
    ACTION_STATE_COMPLETED: ProactiveAction.Status
    class Actionable(_message.Message):
        __slots__ = ("boolean_text",)
        class BooleanText(_message.Message):
            __slots__ = ("approve", "text")
            APPROVE_FIELD_NUMBER: _ClassVar[int]
            TEXT_FIELD_NUMBER: _ClassVar[int]
            approve: bool
            text: str
            def __init__(self, approve: bool = ..., text: _Optional[str] = ...) -> None: ...
        BOOLEAN_TEXT_FIELD_NUMBER: _ClassVar[int]
        boolean_text: ProactiveAction.Actionable.BooleanText
        def __init__(self, boolean_text: _Optional[_Union[ProactiveAction.Actionable.BooleanText, _Mapping]] = ...) -> None: ...
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    ACTIONABLE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    APP_UUIDS_FIELD_NUMBER: _ClassVar[int]
    PROMPT_FOR_SUBAGENT_FIELD_NUMBER: _ClassVar[int]
    title: str
    description: str
    actionable: ProactiveAction.Actionable
    status: ProactiveAction.Status
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    app_uuids: _containers.RepeatedScalarFieldContainer[str]
    prompt_for_subagent: str
    def __init__(self, title: _Optional[str] = ..., description: _Optional[str] = ..., actionable: _Optional[_Union[ProactiveAction.Actionable, _Mapping]] = ..., status: _Optional[_Union[ProactiveAction.Status, str]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., app_uuids: _Optional[_Iterable[str]] = ..., prompt_for_subagent: _Optional[str] = ...) -> None: ...

class ApproveProactiveActionRequest(_message.Message):
    __slots__ = ("entry_id", "user_action")
    ENTRY_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ACTION_FIELD_NUMBER: _ClassVar[int]
    entry_id: int
    user_action: ProactiveAction.Actionable
    def __init__(self, entry_id: _Optional[int] = ..., user_action: _Optional[_Union[ProactiveAction.Actionable, _Mapping]] = ...) -> None: ...

class ApproveProactiveActionResponse(_message.Message):
    __slots__ = ("updated_action",)
    UPDATED_ACTION_FIELD_NUMBER: _ClassVar[int]
    updated_action: ProactiveAction
    def __init__(self, updated_action: _Optional[_Union[ProactiveAction, _Mapping]] = ...) -> None: ...

class CancelProactiveActionRequest(_message.Message):
    __slots__ = ("entry_id",)
    ENTRY_ID_FIELD_NUMBER: _ClassVar[int]
    entry_id: int
    def __init__(self, entry_id: _Optional[int] = ...) -> None: ...

class CancelProactiveActionResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
