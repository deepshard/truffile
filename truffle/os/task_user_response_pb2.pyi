import datetime

from truffle.os import task_target_pb2 as _task_target_pb2
from truffle.common import file_pb2 as _file_pb2
from truffle.common import content_pb2 as _content_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class UserMessage(_message.Message):
    __slots__ = ("content", "attached_feed_entry_ids", "attached_images")
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    ATTACHED_FEED_ENTRY_IDS_FIELD_NUMBER: _ClassVar[int]
    ATTACHED_IMAGES_FIELD_NUMBER: _ClassVar[int]
    content: str
    attached_feed_entry_ids: _containers.RepeatedScalarFieldContainer[int]
    attached_images: _containers.RepeatedCompositeFieldContainer[_content_pb2.AttachedImage]
    def __init__(self, content: _Optional[str] = ..., attached_feed_entry_ids: _Optional[_Iterable[int]] = ..., attached_images: _Optional[_Iterable[_Union[_content_pb2.AttachedImage, _Mapping]]] = ...) -> None: ...

class PendingUserResponse(_message.Message):
    __slots__ = ("task_id", "node_id")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    node_id: int
    def __init__(self, task_id: _Optional[str] = ..., node_id: _Optional[int] = ...) -> None: ...

class RespondToTaskRequest(_message.Message):
    __slots__ = ("steer", "task_id", "node_id", "message", "files")
    STEER_FIELD_NUMBER: _ClassVar[int]
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    steer: bool
    task_id: str
    node_id: int
    message: UserMessage
    files: _containers.RepeatedCompositeFieldContainer[_file_pb2.AttachedFile]
    def __init__(self, steer: bool = ..., task_id: _Optional[str] = ..., node_id: _Optional[int] = ..., message: _Optional[_Union[UserMessage, _Mapping]] = ..., files: _Optional[_Iterable[_Union[_file_pb2.AttachedFile, _Mapping]]] = ...) -> None: ...

class UpdateUserResponseQueueRequest(_message.Message):
    __slots__ = ("task_id", "queued_responses")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    QUEUED_RESPONSES_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    queued_responses: _containers.RepeatedCompositeFieldContainer[QueuedUserResponse]
    def __init__(self, task_id: _Optional[str] = ..., queued_responses: _Optional[_Iterable[_Union[QueuedUserResponse, _Mapping]]] = ...) -> None: ...

class QueuedUserResponse(_message.Message):
    __slots__ = ("uuid", "message", "queued_at", "files")
    UUID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    QUEUED_AT_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    uuid: str
    message: UserMessage
    queued_at: _timestamp_pb2.Timestamp
    files: _containers.RepeatedCompositeFieldContainer[_file_pb2.AttachedFile]
    def __init__(self, uuid: _Optional[str] = ..., message: _Optional[_Union[UserMessage, _Mapping]] = ..., queued_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., files: _Optional[_Iterable[_Union[_file_pb2.AttachedFile, _Mapping]]] = ...) -> None: ...
