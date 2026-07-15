from truffle.common import tool_provider_pb2 as _tool_provider_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TaskError(_message.Message):
    __slots__ = ("is_fatal", "message", "external_tool_provider")
    IS_FATAL_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    EXTERNAL_TOOL_PROVIDER_FIELD_NUMBER: _ClassVar[int]
    is_fatal: bool
    message: str
    external_tool_provider: _tool_provider_pb2.ExternalToolProvidersError
    def __init__(self, is_fatal: bool = ..., message: _Optional[str] = ..., external_tool_provider: _Optional[_Union[_tool_provider_pb2.ExternalToolProvidersError, _Mapping]] = ...) -> None: ...
