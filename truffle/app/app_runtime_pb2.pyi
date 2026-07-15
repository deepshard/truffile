from truffle.app import app_pb2 as _app_pb2
from truffle.common import tool_provider_pb2 as _tool_provider_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AppRuntimeReportErrorRequest(_message.Message):
    __slots__ = ("app_uuid", "error", "needs_intervention")
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    NEEDS_INTERVENTION_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    error: _app_pb2.AppError
    needs_intervention: bool
    def __init__(self, app_uuid: _Optional[str] = ..., error: _Optional[_Union[_app_pb2.AppError, _Mapping]] = ..., needs_intervention: bool = ...) -> None: ...

class AppRuntimeReportErrorResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AppRuntimeGetAppVarRequest(_message.Message):
    __slots__ = ("key",)
    KEY_FIELD_NUMBER: _ClassVar[int]
    key: str
    def __init__(self, key: _Optional[str] = ...) -> None: ...

class AppRuntimeGetAppVarResponse(_message.Message):
    __slots__ = ("key", "value")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: str
    def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class AppRuntimeSetAppVarRequest(_message.Message):
    __slots__ = ("key", "value")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: str
    def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class AppRuntimeSetAppVarResponse(_message.Message):
    __slots__ = ("key", "value")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: str
    def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...

class AppRuntimeDeleteAppVarRequest(_message.Message):
    __slots__ = ("key",)
    KEY_FIELD_NUMBER: _ClassVar[int]
    key: str
    def __init__(self, key: _Optional[str] = ...) -> None: ...

class AppRuntimeDeleteAppVarResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AppRuntimeListAppVarsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AppRuntimeListAppVarsResponse(_message.Message):
    __slots__ = ("vars",)
    class VarsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    VARS_FIELD_NUMBER: _ClassVar[int]
    vars: _containers.ScalarMap[str, str]
    def __init__(self, vars: _Optional[_Mapping[str, str]] = ...) -> None: ...

class AppRuntimeAcquireForegroundMcpRequest(_message.Message):
    __slots__ = ("lease_duration_seconds",)
    LEASE_DURATION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    lease_duration_seconds: int
    def __init__(self, lease_duration_seconds: _Optional[int] = ...) -> None: ...

class AppRuntimeAcquireForegroundMcpResponse(_message.Message):
    __slots__ = ("mcp_server", "lease_duration_seconds")
    MCP_SERVER_FIELD_NUMBER: _ClassVar[int]
    LEASE_DURATION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    mcp_server: _tool_provider_pb2.ExternalToolProvider.ExternalMCPServer
    lease_duration_seconds: int
    def __init__(self, mcp_server: _Optional[_Union[_tool_provider_pb2.ExternalToolProvider.ExternalMCPServer, _Mapping]] = ..., lease_duration_seconds: _Optional[int] = ...) -> None: ...

class AppRuntimeRefreshForegroundMcpRequest(_message.Message):
    __slots__ = ("lease_duration_seconds",)
    LEASE_DURATION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    lease_duration_seconds: int
    def __init__(self, lease_duration_seconds: _Optional[int] = ...) -> None: ...

class AppRuntimeRefreshForegroundMcpResponse(_message.Message):
    __slots__ = ("lease_duration_seconds",)
    LEASE_DURATION_SECONDS_FIELD_NUMBER: _ClassVar[int]
    lease_duration_seconds: int
    def __init__(self, lease_duration_seconds: _Optional[int] = ...) -> None: ...

class AppRuntimeReleaseForegroundMcpRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AppRuntimeReleaseForegroundMcpResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
