from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ToolRecord(_message.Message):
    __slots__ = ("id", "name", "title", "description", "icon_dataurl", "app_uuid", "namespace")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    ICON_DATAURL_FIELD_NUMBER: _ClassVar[int]
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    NAMESPACE_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    title: str
    description: str
    icon_dataurl: str
    app_uuid: str
    namespace: str
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., title: _Optional[str] = ..., description: _Optional[str] = ..., icon_dataurl: _Optional[str] = ..., app_uuid: _Optional[str] = ..., namespace: _Optional[str] = ...) -> None: ...

class ToolsGetToolRequest(_message.Message):
    __slots__ = ("tool_id", "no_icons")
    TOOL_ID_FIELD_NUMBER: _ClassVar[int]
    NO_ICONS_FIELD_NUMBER: _ClassVar[int]
    tool_id: str
    no_icons: bool
    def __init__(self, tool_id: _Optional[str] = ..., no_icons: bool = ...) -> None: ...

class ToolsGetAllToolsRequest(_message.Message):
    __slots__ = ("no_icons",)
    NO_ICONS_FIELD_NUMBER: _ClassVar[int]
    no_icons: bool
    def __init__(self, no_icons: bool = ...) -> None: ...

class ToolsGetToolsForAppRequest(_message.Message):
    __slots__ = ("app_uuid", "no_icons")
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    NO_ICONS_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    no_icons: bool
    def __init__(self, app_uuid: _Optional[str] = ..., no_icons: bool = ...) -> None: ...

class ToolRecordList(_message.Message):
    __slots__ = ("tools",)
    TOOLS_FIELD_NUMBER: _ClassVar[int]
    tools: _containers.RepeatedCompositeFieldContainer[ToolRecord]
    def __init__(self, tools: _Optional[_Iterable[_Union[ToolRecord, _Mapping]]] = ...) -> None: ...
