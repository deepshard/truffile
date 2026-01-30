from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from typing import ClassVar as _ClassVar

DESCRIPTOR: _descriptor.FileDescriptor

class AppType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    APP_TYPE_INVALID: _ClassVar[AppType]
    APP_TYPE_FOREGROUND: _ClassVar[AppType]
    APP_TYPE_BACKGROUND: _ClassVar[AppType]
    APP_TYPE_SYSTEM: _ClassVar[AppType]
APP_TYPE_INVALID: AppType
APP_TYPE_FOREGROUND: AppType
APP_TYPE_BACKGROUND: AppType
APP_TYPE_SYSTEM: AppType
