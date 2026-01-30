from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ExternalToolProvider(_message.Message):
    __slots__ = ("uuid", "mcp_server")
    class ExternalMCPServer(_message.Message):
        __slots__ = ("address", "port", "path")
        ADDRESS_FIELD_NUMBER: _ClassVar[int]
        PORT_FIELD_NUMBER: _ClassVar[int]
        PATH_FIELD_NUMBER: _ClassVar[int]
        address: str
        port: int
        path: str
        def __init__(self, address: _Optional[str] = ..., port: _Optional[int] = ..., path: _Optional[str] = ...) -> None: ...
    UUID_FIELD_NUMBER: _ClassVar[int]
    MCP_SERVER_FIELD_NUMBER: _ClassVar[int]
    uuid: str
    mcp_server: ExternalToolProvider.ExternalMCPServer
    def __init__(self, uuid: _Optional[str] = ..., mcp_server: _Optional[_Union[ExternalToolProvider.ExternalMCPServer, _Mapping]] = ...) -> None: ...

class ExternalToolProvidersError(_message.Message):
    __slots__ = ("provider_uuid", "error", "details")
    PROVIDER_UUID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    provider_uuid: str
    error: str
    details: str
    def __init__(self, provider_uuid: _Optional[str] = ..., error: _Optional[str] = ..., details: _Optional[str] = ...) -> None: ...
