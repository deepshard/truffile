from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class TargetTask(_message.Message):
    __slots__ = ("task_id", "node_id")
    TASK_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    task_id: str
    node_id: int
    def __init__(self, task_id: _Optional[str] = ..., node_id: _Optional[int] = ...) -> None: ...
