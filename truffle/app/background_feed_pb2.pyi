from google.protobuf import timestamp_pb2 as _timestamp_pb2
from truffle.common import content_pb2 as _content_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FeedCard(_message.Message):
    __slots__ = ("title", "body", "media_sources", "source_uri", "content_timestamp", "metadata")
    TITLE_FIELD_NUMBER: _ClassVar[int]
    BODY_FIELD_NUMBER: _ClassVar[int]
    MEDIA_SOURCES_FIELD_NUMBER: _ClassVar[int]
    SOURCE_URI_FIELD_NUMBER: _ClassVar[int]
    CONTENT_TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    title: str
    body: str
    media_sources: _containers.RepeatedCompositeFieldContainer[_content_pb2.MediaSource]
    source_uri: str
    content_timestamp: _timestamp_pb2.Timestamp
    metadata: _struct_pb2.Struct
    def __init__(self, title: _Optional[str] = ..., body: _Optional[str] = ..., media_sources: _Optional[_Iterable[_Union[_content_pb2.MediaSource, _Mapping]]] = ..., source_uri: _Optional[str] = ..., content_timestamp: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., metadata: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class BackgroundFeed(_message.Message):
    __slots__ = ("entries",)
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[FeedEntry]
    def __init__(self, entries: _Optional[_Iterable[_Union[FeedEntry, _Mapping]]] = ...) -> None: ...

class FeedEntry(_message.Message):
    __slots__ = ("id", "app_uuid", "timestamp", "card", "likes")
    ID_FIELD_NUMBER: _ClassVar[int]
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    CARD_FIELD_NUMBER: _ClassVar[int]
    LIKES_FIELD_NUMBER: _ClassVar[int]
    id: int
    app_uuid: str
    timestamp: _timestamp_pb2.Timestamp
    card: FeedCard
    likes: int
    def __init__(self, id: _Optional[int] = ..., app_uuid: _Optional[str] = ..., timestamp: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., card: _Optional[_Union[FeedCard, _Mapping]] = ..., likes: _Optional[int] = ...) -> None: ...

class FeedEntryTaskContext(_message.Message):
    __slots__ = ("entries",)
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[FeedEntry]
    def __init__(self, entries: _Optional[_Iterable[_Union[FeedEntry, _Mapping]]] = ...) -> None: ...
