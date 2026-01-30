from truffle.app import background_pb2 as _background_pb2
from truffle.app import background_feed_pb2 as _background_feed_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetBackgroundFeedRequest(_message.Message):
    __slots__ = ("target_entry_id", "max_before", "max_after")
    TARGET_ENTRY_ID_FIELD_NUMBER: _ClassVar[int]
    MAX_BEFORE_FIELD_NUMBER: _ClassVar[int]
    MAX_AFTER_FIELD_NUMBER: _ClassVar[int]
    target_entry_id: int
    max_before: int
    max_after: int
    def __init__(self, target_entry_id: _Optional[int] = ..., max_before: _Optional[int] = ..., max_after: _Optional[int] = ...) -> None: ...

class GetBackgroundFeedResponse(_message.Message):
    __slots__ = ("entries",)
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[_background_feed_pb2.FeedEntry]
    def __init__(self, entries: _Optional[_Iterable[_Union[_background_feed_pb2.FeedEntry, _Mapping]]] = ...) -> None: ...

class LikeBackgroundFeedEntryRequest(_message.Message):
    __slots__ = ("feed_entry_id", "increment")
    FEED_ENTRY_ID_FIELD_NUMBER: _ClassVar[int]
    INCREMENT_FIELD_NUMBER: _ClassVar[int]
    feed_entry_id: int
    increment: int
    def __init__(self, feed_entry_id: _Optional[int] = ..., increment: _Optional[int] = ...) -> None: ...

class LikeBackgroundFeedEntryResponse(_message.Message):
    __slots__ = ("new_like_count",)
    NEW_LIKE_COUNT_FIELD_NUMBER: _ClassVar[int]
    new_like_count: int
    def __init__(self, new_like_count: _Optional[int] = ...) -> None: ...

class GetLatestFeedEntryIDRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetLatestFeedEntryIDResponse(_message.Message):
    __slots__ = ("latest_feed_entry_id",)
    LATEST_FEED_ENTRY_ID_FIELD_NUMBER: _ClassVar[int]
    latest_feed_entry_id: int
    def __init__(self, latest_feed_entry_id: _Optional[int] = ...) -> None: ...

class BackgroundFeedFeedbackRequest(_message.Message):
    __slots__ = ("associated_feed_entries", "feedback")
    ASSOCIATED_FEED_ENTRIES_FIELD_NUMBER: _ClassVar[int]
    FEEDBACK_FIELD_NUMBER: _ClassVar[int]
    associated_feed_entries: _containers.RepeatedScalarFieldContainer[int]
    feedback: str
    def __init__(self, associated_feed_entries: _Optional[_Iterable[int]] = ..., feedback: _Optional[str] = ...) -> None: ...

class BackgroundFeedFeedbackResponse(_message.Message):
    __slots__ = ("feedback_uuid",)
    FEEDBACK_UUID_FIELD_NUMBER: _ClassVar[int]
    feedback_uuid: str
    def __init__(self, feedback_uuid: _Optional[str] = ...) -> None: ...
