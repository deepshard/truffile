from truffle.app import app_pb2 as _app_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetAllAppsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetAllAppsResponse(_message.Message):
    __slots__ = ("apps",)
    APPS_FIELD_NUMBER: _ClassVar[int]
    apps: _containers.RepeatedCompositeFieldContainer[_app_pb2.App]
    def __init__(self, apps: _Optional[_Iterable[_Union[_app_pb2.App, _Mapping]]] = ...) -> None: ...

class DeleteAppRequest(_message.Message):
    __slots__ = ("app_uuid",)
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    def __init__(self, app_uuid: _Optional[str] = ...) -> None: ...

class DeleteAppResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
