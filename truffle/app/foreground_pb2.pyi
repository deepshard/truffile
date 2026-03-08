from truffle.app import app_build_pb2 as _app_build_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ForegroundApp(_message.Message):
    __slots__ = ("available_tools",)
    class AvailableTool(_message.Message):
        __slots__ = ("tool_name", "tool_description", "args_schema")
        TOOL_NAME_FIELD_NUMBER: _ClassVar[int]
        TOOL_DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
        ARGS_SCHEMA_FIELD_NUMBER: _ClassVar[int]
        tool_name: str
        tool_description: str
        args_schema: str
        def __init__(self, tool_name: _Optional[str] = ..., tool_description: _Optional[str] = ..., args_schema: _Optional[str] = ...) -> None: ...
    AVAILABLE_TOOLS_FIELD_NUMBER: _ClassVar[int]
    available_tools: _containers.RepeatedCompositeFieldContainer[ForegroundApp.AvailableTool]
    def __init__(self, available_tools: _Optional[_Iterable[_Union[ForegroundApp.AvailableTool, _Mapping]]] = ...) -> None: ...

class ForegroundAppBuildInfo(_message.Message):
    __slots__ = ("process",)
    PROCESS_FIELD_NUMBER: _ClassVar[int]
    process: _app_build_pb2.ProcessConfig
    def __init__(self, process: _Optional[_Union[_app_build_pb2.ProcessConfig, _Mapping]] = ...) -> None: ...
