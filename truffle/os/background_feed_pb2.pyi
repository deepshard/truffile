import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from truffle.common import content_pb2 as _content_pb2
from truffle.os import proactivity_pb2 as _proactivity_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FeedCard(_message.Message):
    __slots__ = ("title", "body", "media_sources", "source_uri", "created_at", "metadata")
    TITLE_FIELD_NUMBER: _ClassVar[int]
    BODY_FIELD_NUMBER: _ClassVar[int]
    MEDIA_SOURCES_FIELD_NUMBER: _ClassVar[int]
    SOURCE_URI_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    title: str
    body: str
    media_sources: _containers.RepeatedCompositeFieldContainer[_content_pb2.MediaSource]
    source_uri: str
    created_at: _timestamp_pb2.Timestamp
    metadata: _struct_pb2.Struct
    def __init__(self, title: _Optional[str] = ..., body: _Optional[str] = ..., media_sources: _Optional[_Iterable[_Union[_content_pb2.MediaSource, _Mapping]]] = ..., source_uri: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., metadata: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class BackgroundFeed(_message.Message):
    __slots__ = ("entries",)
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[FeedEntry]
    def __init__(self, entries: _Optional[_Iterable[_Union[FeedEntry, _Mapping]]] = ...) -> None: ...

class FeedEntryNotification(_message.Message):
    __slots__ = ("entry_ids", "operation")
    class Operation(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        OPERATION_INVALID: _ClassVar[FeedEntryNotification.Operation]
        OPERATION_ADD: _ClassVar[FeedEntryNotification.Operation]
        OPERATION_DELETE: _ClassVar[FeedEntryNotification.Operation]
        OPERATION_REFRESH: _ClassVar[FeedEntryNotification.Operation]
    OPERATION_INVALID: FeedEntryNotification.Operation
    OPERATION_ADD: FeedEntryNotification.Operation
    OPERATION_DELETE: FeedEntryNotification.Operation
    OPERATION_REFRESH: FeedEntryNotification.Operation
    ENTRY_IDS_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    entry_ids: _containers.RepeatedScalarFieldContainer[int]
    operation: FeedEntryNotification.Operation
    def __init__(self, entry_ids: _Optional[_Iterable[int]] = ..., operation: _Optional[_Union[FeedEntryNotification.Operation, str]] = ...) -> None: ...

class FeedEntry(_message.Message):
    __slots__ = ("id", "card", "proactive_action", "timestamp")
    ID_FIELD_NUMBER: _ClassVar[int]
    CARD_FIELD_NUMBER: _ClassVar[int]
    PROACTIVE_ACTION_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    id: int
    card: FeedCard
    proactive_action: _proactivity_pb2.ProactiveAction
    timestamp: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., card: _Optional[_Union[FeedCard, _Mapping]] = ..., proactive_action: _Optional[_Union[_proactivity_pb2.ProactiveAction, _Mapping]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class FeedEntryTaskContext(_message.Message):
    __slots__ = ("entries",)
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[FeedEntry]
    def __init__(self, entries: _Optional[_Iterable[_Union[FeedEntry, _Mapping]]] = ...) -> None: ...
