from truffle.os import task_target_pb2 as _task_target_pb2
from truffle.common import file_pb2 as _file_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class UserMessage(_message.Message):
    __slots__ = ("content", "attached_feed_entry_ids")
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    ATTACHED_FEED_ENTRY_IDS_FIELD_NUMBER: _ClassVar[int]
    content: str
    attached_feed_entry_ids: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, content: _Optional[str] = ..., attached_feed_entry_ids: _Optional[_Iterable[int]] = ...) -> None: ...

class PendingUserResponse(_message.Message):
    __slots__ = ("task_id", "node_id")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    node_id: int
    def __init__(self, task_id: _Optional[str] = ..., node_id: _Optional[int] = ...) -> None: ...

class RespondToTaskRequest(_message.Message):
    __slots__ = ("task_id", "node_id", "message", "files")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    FILES_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    node_id: int
    message: UserMessage
    files: _containers.RepeatedCompositeFieldContainer[_file_pb2.AttachedFile]
    def __init__(self, task_id: _Optional[str] = ..., node_id: _Optional[int] = ..., message: _Optional[_Union[UserMessage, _Mapping]] = ..., files: _Optional[_Iterable[_Union[_file_pb2.AttachedFile, _Mapping]]] = ...) -> None: ...
