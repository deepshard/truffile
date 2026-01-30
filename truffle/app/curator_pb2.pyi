from truffle.app import background_feed_pb2 as _background_feed_pb2
from truffle.app import background_pb2 as _background_pb2
from truffle.os import background_feed_queries_pb2 as _background_feed_queries_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TakeFeedbackResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class TakeFeedbackRequest(_message.Message):
    __slots__ = ("feedback", "feedback_request_uuid")
    FEEDBACK_FIELD_NUMBER: _ClassVar[int]
    FEEDBACK_REQUEST_UUID_FIELD_NUMBER: _ClassVar[int]
    feedback: _background_feed_queries_pb2.BackgroundFeedFeedbackRequest
    feedback_request_uuid: str
    def __init__(self, feedback: _Optional[_Union[_background_feed_queries_pb2.BackgroundFeedFeedbackRequest, _Mapping]] = ..., feedback_request_uuid: _Optional[str] = ...) -> None: ...

class FeedOperation(_message.Message):
    __slots__ = ("feed_entry_id", "operation", "updated_card")
    FEED_ENTRY_ID_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    UPDATED_CARD_FIELD_NUMBER: _ClassVar[int]
    feed_entry_id: int
    operation: _background_pb2.BackgroundAppNotification.Operation
    updated_card: _background_feed_pb2.FeedCard
    def __init__(self, feed_entry_id: _Optional[int] = ..., operation: _Optional[_Union[_background_pb2.BackgroundAppNotification.Operation, str]] = ..., updated_card: _Optional[_Union[_background_feed_pb2.FeedCard, _Mapping]] = ...) -> None: ...

class HandleNewPostRequest(_message.Message):
    __slots__ = ("new_post",)
    NEW_POST_FIELD_NUMBER: _ClassVar[int]
    new_post: _background_feed_pb2.FeedEntry
    def __init__(self, new_post: _Optional[_Union[_background_feed_pb2.FeedEntry, _Mapping]] = ...) -> None: ...

class HandleNewPostResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CuratorState(_message.Message):
    __slots__ = ("state_json",)
    STATE_JSON_FIELD_NUMBER: _ClassVar[int]
    state_json: str
    def __init__(self, state_json: _Optional[str] = ...) -> None: ...

class FeedControlRequest(_message.Message):
    __slots__ = ("last_known_state", "curator_user_session_token")
    LAST_KNOWN_STATE_FIELD_NUMBER: _ClassVar[int]
    CURATOR_USER_SESSION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    last_known_state: CuratorState
    curator_user_session_token: str
    def __init__(self, last_known_state: _Optional[_Union[CuratorState, _Mapping]] = ..., curator_user_session_token: _Optional[str] = ...) -> None: ...

class FeedbackProcessed(_message.Message):
    __slots__ = ("feedback_request_uuid",)
    FEEDBACK_REQUEST_UUID_FIELD_NUMBER: _ClassVar[int]
    feedback_request_uuid: str
    def __init__(self, feedback_request_uuid: _Optional[str] = ...) -> None: ...

class FeedControlResponse(_message.Message):
    __slots__ = ("operation", "state_to_save", "feedback_done")
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    STATE_TO_SAVE_FIELD_NUMBER: _ClassVar[int]
    FEEDBACK_DONE_FIELD_NUMBER: _ClassVar[int]
    operation: FeedOperation
    state_to_save: CuratorState
    feedback_done: FeedbackProcessed
    def __init__(self, operation: _Optional[_Union[FeedOperation, _Mapping]] = ..., state_to_save: _Optional[_Union[CuratorState, _Mapping]] = ..., feedback_done: _Optional[_Union[FeedbackProcessed, _Mapping]] = ...) -> None: ...
