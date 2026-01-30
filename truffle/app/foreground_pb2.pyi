from truffle.common import icon_pb2 as _icon_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ForegroundApp(_message.Message):
    __slots__ = ("uuid", "metadata")
    class Metadata(_message.Message):
        __slots__ = ("name", "icon", "description")
        NAME_FIELD_NUMBER: _ClassVar[int]
        ICON_FIELD_NUMBER: _ClassVar[int]
        DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
        name: str
        icon: _icon_pb2.Icon
        description: str
        def __init__(self, name: _Optional[str] = ..., icon: _Optional[_Union[_icon_pb2.Icon, _Mapping]] = ..., description: _Optional[str] = ...) -> None: ...
    UUID_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    uuid: str
    metadata: ForegroundApp.Metadata
    def __init__(self, uuid: _Optional[str] = ..., metadata: _Optional[_Union[ForegroundApp.Metadata, _Mapping]] = ...) -> None: ...

class ForegroundAppBuildInfo(_message.Message):
    __slots__ = ("metadata",)
    METADATA_FIELD_NUMBER: _ClassVar[int]
    metadata: ForegroundApp.Metadata
    def __init__(self, metadata: _Optional[_Union[ForegroundApp.Metadata, _Mapping]] = ...) -> None: ...
