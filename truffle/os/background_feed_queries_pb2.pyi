from truffle.app import background_pb2 as _background_pb2
from truffle.os import background_feed_pb2 as _background_feed_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetBackgroundFeedRequest(_message.Message):
    __slots__ = ("target_entry_id", "max_before", "max_after", "include_actions", "include_cards")
    TARGET_ENTRY_ID_FIELD_NUMBER: _ClassVar[int]
    MAX_BEFORE_FIELD_NUMBER: _ClassVar[int]
    MAX_AFTER_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_ACTIONS_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_CARDS_FIELD_NUMBER: _ClassVar[int]
    target_entry_id: int
    max_before: int
    max_after: int
    include_actions: bool
    include_cards: bool
    def __init__(self, target_entry_id: _Optional[int] = ..., max_before: _Optional[int] = ..., max_after: _Optional[int] = ..., include_actions: bool = ..., include_cards: bool = ...) -> None: ...

class GetBackgroundFeedResponse(_message.Message):
    __slots__ = ("entries",)
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[_background_feed_pb2.FeedEntry]
    def __init__(self, entries: _Optional[_Iterable[_Union[_background_feed_pb2.FeedEntry, _Mapping]]] = ...) -> None: ...

class GetLatestFeedEntryIDRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetLatestFeedEntryIDResponse(_message.Message):
    __slots__ = ("latest_feed_entry_id",)
    LATEST_FEED_ENTRY_ID_FIELD_NUMBER: _ClassVar[int]
    latest_feed_entry_id: int
    def __init__(self, latest_feed_entry_id: _Optional[int] = ...) -> None: ...
