import datetime

from truffle.common import icon_pb2 as _icon_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from truffle.app import app_pb2 as _app_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DefaultAppManifest(_message.Message):
    __slots__ = ("version", "generated_at", "apps")
    class DefaultApp(_message.Message):
        __slots__ = ("index", "bundle_url", "metadata", "bundle_md5", "provides_foreground", "provides_background")
        INDEX_FIELD_NUMBER: _ClassVar[int]
        BUNDLE_URL_FIELD_NUMBER: _ClassVar[int]
        METADATA_FIELD_NUMBER: _ClassVar[int]
        BUNDLE_MD5_FIELD_NUMBER: _ClassVar[int]
        PROVIDES_FOREGROUND_FIELD_NUMBER: _ClassVar[int]
        PROVIDES_BACKGROUND_FIELD_NUMBER: _ClassVar[int]
        index: int
        bundle_url: str
        metadata: _app_pb2.AppMetadata
        bundle_md5: str
        provides_foreground: bool
        provides_background: bool
        def __init__(self, index: _Optional[int] = ..., bundle_url: _Optional[str] = ..., metadata: _Optional[_Union[_app_pb2.AppMetadata, _Mapping]] = ..., bundle_md5: _Optional[str] = ..., provides_foreground: bool = ..., provides_background: bool = ...) -> None: ...
    VERSION_FIELD_NUMBER: _ClassVar[int]
    GENERATED_AT_FIELD_NUMBER: _ClassVar[int]
    APPS_FIELD_NUMBER: _ClassVar[int]
    version: str
    generated_at: _timestamp_pb2.Timestamp
    apps: _containers.RepeatedCompositeFieldContainer[DefaultAppManifest.DefaultApp]
    def __init__(self, version: _Optional[str] = ..., generated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., apps: _Optional[_Iterable[_Union[DefaultAppManifest.DefaultApp, _Mapping]]] = ...) -> None: ...
