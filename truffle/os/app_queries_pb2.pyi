from truffle.app import foreground_pb2 as _foreground_pb2
from truffle.app import background_pb2 as _background_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetForegroundAppsRequest(_message.Message):
    __slots__ = ("uuids",)
    UUIDS_FIELD_NUMBER: _ClassVar[int]
    uuids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, uuids: _Optional[_Iterable[str]] = ...) -> None: ...

class GetForegroundAppsResponse(_message.Message):
    __slots__ = ("apps",)
    APPS_FIELD_NUMBER: _ClassVar[int]
    apps: _containers.RepeatedCompositeFieldContainer[_foreground_pb2.ForegroundApp]
    def __init__(self, apps: _Optional[_Iterable[_Union[_foreground_pb2.ForegroundApp, _Mapping]]] = ...) -> None: ...

class GetBackgroundAppsRequest(_message.Message):
    __slots__ = ("uuids",)
    UUIDS_FIELD_NUMBER: _ClassVar[int]
    uuids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, uuids: _Optional[_Iterable[str]] = ...) -> None: ...

class GetBackgroundAppsResponse(_message.Message):
    __slots__ = ("apps",)
    APPS_FIELD_NUMBER: _ClassVar[int]
    apps: _containers.RepeatedCompositeFieldContainer[_background_pb2.BackgroundApp]
    def __init__(self, apps: _Optional[_Iterable[_Union[_background_pb2.BackgroundApp, _Mapping]]] = ...) -> None: ...

class GetAllAppsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetAllAppsResponse(_message.Message):
    __slots__ = ("foreground_apps", "background_apps")
    FOREGROUND_APPS_FIELD_NUMBER: _ClassVar[int]
    BACKGROUND_APPS_FIELD_NUMBER: _ClassVar[int]
    foreground_apps: _containers.RepeatedCompositeFieldContainer[_foreground_pb2.ForegroundApp]
    background_apps: _containers.RepeatedCompositeFieldContainer[_background_pb2.BackgroundApp]
    def __init__(self, foreground_apps: _Optional[_Iterable[_Union[_foreground_pb2.ForegroundApp, _Mapping]]] = ..., background_apps: _Optional[_Iterable[_Union[_background_pb2.BackgroundApp, _Mapping]]] = ...) -> None: ...

class DeleteAppRequest(_message.Message):
    __slots__ = ("app_uuid",)
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    def __init__(self, app_uuid: _Optional[str] = ...) -> None: ...

class DeleteAppResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
