import datetime

from truffle.common import icon_pb2 as _icon_pb2
from truffle.app import foreground_pb2 as _foreground_pb2
from truffle.app import background_pb2 as _background_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AppMetadata(_message.Message):
    __slots__ = ("name", "icon", "description", "bundle_id")
    NAME_FIELD_NUMBER: _ClassVar[int]
    ICON_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    BUNDLE_ID_FIELD_NUMBER: _ClassVar[int]
    name: str
    icon: _icon_pb2.Icon
    description: str
    bundle_id: str
    def __init__(self, name: _Optional[str] = ..., icon: _Optional[_Union[_icon_pb2.Icon, _Mapping]] = ..., description: _Optional[str] = ..., bundle_id: _Optional[str] = ...) -> None: ...

class AppConfig(_message.Message):
    __slots__ = ("can_reconfigure",)
    CAN_RECONFIGURE_FIELD_NUMBER: _ClassVar[int]
    can_reconfigure: bool
    def __init__(self, can_reconfigure: bool = ...) -> None: ...

class App(_message.Message):
    __slots__ = ("uuid", "metadata", "foreground", "background", "error", "config", "installed_at", "last_updated_at")
    UUID_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    FOREGROUND_FIELD_NUMBER: _ClassVar[int]
    BACKGROUND_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    INSTALLED_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    uuid: str
    metadata: AppMetadata
    foreground: _foreground_pb2.ForegroundApp
    background: _background_pb2.BackgroundApp
    error: AppError
    config: AppConfig
    installed_at: _timestamp_pb2.Timestamp
    last_updated_at: _timestamp_pb2.Timestamp
    def __init__(self, uuid: _Optional[str] = ..., metadata: _Optional[_Union[AppMetadata, _Mapping]] = ..., foreground: _Optional[_Union[_foreground_pb2.ForegroundApp, _Mapping]] = ..., background: _Optional[_Union[_background_pb2.BackgroundApp, _Mapping]] = ..., error: _Optional[_Union[AppError, _Mapping]] = ..., config: _Optional[_Union[AppConfig, _Mapping]] = ..., installed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., last_updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class AppError(_message.Message):
    __slots__ = ("error_type", "error_message")
    class ErrorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        APP_ERROR_TYPE_INVALID: _ClassVar[AppError.ErrorType]
        APP_ERROR_RUNTIME: _ClassVar[AppError.ErrorType]
        APP_ERROR_AUTH: _ClassVar[AppError.ErrorType]
        APP_ERROR_UNKNOWN: _ClassVar[AppError.ErrorType]
    APP_ERROR_TYPE_INVALID: AppError.ErrorType
    APP_ERROR_RUNTIME: AppError.ErrorType
    APP_ERROR_AUTH: AppError.ErrorType
    APP_ERROR_UNKNOWN: AppError.ErrorType
    ERROR_TYPE_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    error_type: AppError.ErrorType
    error_message: str
    def __init__(self, error_type: _Optional[_Union[AppError.ErrorType, str]] = ..., error_message: _Optional[str] = ...) -> None: ...
