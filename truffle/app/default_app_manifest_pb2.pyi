from truffle.app import app_type_pb2 as _app_type_pb2
from truffle.common import icon_pb2 as _icon_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DefaultAppManifest(_message.Message):
    __slots__ = ("version", "generated_at", "apps")
    class DefaultApp(_message.Message):
        __slots__ = ("app_type", "name", "bundle_url", "icon", "bundle_md5", "description")
        APP_TYPE_FIELD_NUMBER: _ClassVar[int]
        NAME_FIELD_NUMBER: _ClassVar[int]
        BUNDLE_URL_FIELD_NUMBER: _ClassVar[int]
        ICON_FIELD_NUMBER: _ClassVar[int]
        BUNDLE_MD5_FIELD_NUMBER: _ClassVar[int]
        DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
        app_type: _app_type_pb2.AppType
        name: str
        bundle_url: str
        icon: _icon_pb2.Icon
        bundle_md5: str
        description: str
        def __init__(self, app_type: _Optional[_Union[_app_type_pb2.AppType, str]] = ..., name: _Optional[str] = ..., bundle_url: _Optional[str] = ..., icon: _Optional[_Union[_icon_pb2.Icon, _Mapping]] = ..., bundle_md5: _Optional[str] = ..., description: _Optional[str] = ...) -> None: ...
    VERSION_FIELD_NUMBER: _ClassVar[int]
    GENERATED_AT_FIELD_NUMBER: _ClassVar[int]
    APPS_FIELD_NUMBER: _ClassVar[int]
    version: str
    generated_at: _timestamp_pb2.Timestamp
    apps: _containers.RepeatedCompositeFieldContainer[DefaultAppManifest.DefaultApp]
    def __init__(self, version: _Optional[str] = ..., generated_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., apps: _Optional[_Iterable[_Union[DefaultAppManifest.DefaultApp, _Mapping]]] = ...) -> None: ...
