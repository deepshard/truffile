from truffle.app import app_pb2 as _app_pb2
from truffle.app import background_pb2 as _background_pb2
from truffle.app import foreground_pb2 as _foreground_pb2
from truffle.common import schedule_pb2 as _schedule_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union
from truffle.app.app_pb2 import AppMetadata as AppMetadata
from truffle.app.app_pb2 import AppConfig as AppConfig
from truffle.app.app_pb2 import AppBundleRelease as AppBundleRelease
from truffle.app.app_pb2 import InstalledAppBundle as InstalledAppBundle
from truffle.app.app_pb2 import App as App
from truffle.app.app_pb2 import AppError as AppError
from truffle.app.background_pb2 import BackgroundAppRuntimePolicy as BackgroundAppRuntimePolicy
from truffle.app.background_pb2 import BackgroundApp as BackgroundApp
from truffle.app.background_pb2 import BackgroundAppBuildInfo as BackgroundAppBuildInfo
from truffle.app.background_pb2 import BackgroundContext as BackgroundContext
from truffle.app.background_pb2 import BackgroundAppSubmitContextRequest as BackgroundAppSubmitContextRequest
from truffle.app.background_pb2 import BackgroundAppSubmitContextResponse as BackgroundAppSubmitContextResponse
from truffle.app.background_pb2 import BackgroundAppOnRunRequest as BackgroundAppOnRunRequest
from truffle.app.background_pb2 import BackgroundAppOnRunResponse as BackgroundAppOnRunResponse
from truffle.app.background_pb2 import BackgroundAppYieldRequest as BackgroundAppYieldRequest
from truffle.app.background_pb2 import BackgroundAppYieldResponse as BackgroundAppYieldResponse
from truffle.app.background_pb2 import BackgroundAppReportErrorResponse as BackgroundAppReportErrorResponse
from truffle.app.foreground_pb2 import ForegroundApp as ForegroundApp
from truffle.app.foreground_pb2 import ForegroundAppBuildInfo as ForegroundAppBuildInfo

DESCRIPTOR: _descriptor.FileDescriptor

class GetAllAppsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetAllAppsResponse(_message.Message):
    __slots__ = ("apps",)
    APPS_FIELD_NUMBER: _ClassVar[int]
    apps: _containers.RepeatedCompositeFieldContainer[_app_pb2.App]
    def __init__(self, apps: _Optional[_Iterable[_Union[_app_pb2.App, _Mapping]]] = ...) -> None: ...

class GetAppRequest(_message.Message):
    __slots__ = ("app_uuid",)
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    def __init__(self, app_uuid: _Optional[str] = ...) -> None: ...

class GetAppResponse(_message.Message):
    __slots__ = ("app",)
    APP_FIELD_NUMBER: _ClassVar[int]
    app: _app_pb2.App
    def __init__(self, app: _Optional[_Union[_app_pb2.App, _Mapping]] = ...) -> None: ...

class DeleteAppRequest(_message.Message):
    __slots__ = ("app_uuid",)
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    def __init__(self, app_uuid: _Optional[str] = ...) -> None: ...

class DeleteAppResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SetAppSettingsRequest(_message.Message):
    __slots__ = ("app_uuid", "fg_settings", "bg_settings", "bg_runtime_policy")
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    FG_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    BG_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    BG_RUNTIME_POLICY_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    fg_settings: _foreground_pb2.ForegroundApp.Settings
    bg_settings: _background_pb2.BackgroundApp.Settings
    bg_runtime_policy: _background_pb2.BackgroundAppRuntimePolicy
    def __init__(self, app_uuid: _Optional[str] = ..., fg_settings: _Optional[_Union[_foreground_pb2.ForegroundApp.Settings, _Mapping]] = ..., bg_settings: _Optional[_Union[_background_pb2.BackgroundApp.Settings, _Mapping]] = ..., bg_runtime_policy: _Optional[_Union[_background_pb2.BackgroundAppRuntimePolicy, _Mapping]] = ...) -> None: ...

class SetAppSettingsResponse(_message.Message):
    __slots__ = ("app",)
    APP_FIELD_NUMBER: _ClassVar[int]
    app: _app_pb2.App
    def __init__(self, app: _Optional[_Union[_app_pb2.App, _Mapping]] = ...) -> None: ...

class ListBackgroundAppsRequest(_message.Message):
    __slots__ = ("limit", "offset")
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    limit: int
    offset: int
    def __init__(self, limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ListBackgroundAppsResponse(_message.Message):
    __slots__ = ("apps",)
    APPS_FIELD_NUMBER: _ClassVar[int]
    apps: _containers.RepeatedCompositeFieldContainer[_app_pb2.App]
    def __init__(self, apps: _Optional[_Iterable[_Union[_app_pb2.App, _Mapping]]] = ...) -> None: ...

class SetBackgroundAppEnabledRequest(_message.Message):
    __slots__ = ("app_uuid", "enabled")
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    enabled: bool
    def __init__(self, app_uuid: _Optional[str] = ..., enabled: bool = ...) -> None: ...

class SetBackgroundAppEnabledResponse(_message.Message):
    __slots__ = ("app",)
    APP_FIELD_NUMBER: _ClassVar[int]
    app: _app_pb2.App
    def __init__(self, app: _Optional[_Union[_app_pb2.App, _Mapping]] = ...) -> None: ...

class UpdateBackgroundAppScheduleRequest(_message.Message):
    __slots__ = ("app_uuid", "schedule", "runtime_policy")
    APP_UUID_FIELD_NUMBER: _ClassVar[int]
    SCHEDULE_FIELD_NUMBER: _ClassVar[int]
    RUNTIME_POLICY_FIELD_NUMBER: _ClassVar[int]
    app_uuid: str
    schedule: _schedule_pb2.RunSchedulePolicy
    runtime_policy: _background_pb2.BackgroundAppRuntimePolicy
    def __init__(self, app_uuid: _Optional[str] = ..., schedule: _Optional[_Union[_schedule_pb2.RunSchedulePolicy, _Mapping]] = ..., runtime_policy: _Optional[_Union[_background_pb2.BackgroundAppRuntimePolicy, _Mapping]] = ...) -> None: ...

class UpdateBackgroundAppScheduleResponse(_message.Message):
    __slots__ = ("app", "schedule", "runtime_policy")
    APP_FIELD_NUMBER: _ClassVar[int]
    SCHEDULE_FIELD_NUMBER: _ClassVar[int]
    RUNTIME_POLICY_FIELD_NUMBER: _ClassVar[int]
    app: _app_pb2.App
    schedule: _schedule_pb2.RunSchedulePolicy
    runtime_policy: _background_pb2.BackgroundAppRuntimePolicy
    def __init__(self, app: _Optional[_Union[_app_pb2.App, _Mapping]] = ..., schedule: _Optional[_Union[_schedule_pb2.RunSchedulePolicy, _Mapping]] = ..., runtime_policy: _Optional[_Union[_background_pb2.BackgroundAppRuntimePolicy, _Mapping]] = ...) -> None: ...
