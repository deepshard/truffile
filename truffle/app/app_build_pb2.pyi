from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ProcessConfig(_message.Message):
    __slots__ = ("cmd", "args", "env", "cwd")
    CMD_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    ENV_FIELD_NUMBER: _ClassVar[int]
    CWD_FIELD_NUMBER: _ClassVar[int]
    cmd: str
    args: _containers.RepeatedScalarFieldContainer[str]
    env: _containers.RepeatedScalarFieldContainer[str]
    cwd: str
    def __init__(self, cmd: _Optional[str] = ..., args: _Optional[_Iterable[str]] = ..., env: _Optional[_Iterable[str]] = ..., cwd: _Optional[str] = ...) -> None: ...
