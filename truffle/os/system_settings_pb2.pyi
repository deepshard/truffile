from truffle.os import hardware_settings_pb2 as _hardware_settings_pb2
from truffle.os import dream_pb2 as _dream_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union
from truffle.os.hardware_settings_pb2 import HardwareSettings as HardwareSettings
from truffle.os.dream_pb2 import DreamModeSettings as DreamModeSettings
from truffle.os.dream_pb2 import DreamModeStatus as DreamModeStatus
from truffle.os.dream_pb2 import GetDreamModeStatusRequest as GetDreamModeStatusRequest
from truffle.os.dream_pb2 import GetDreamModeStatusResponse as GetDreamModeStatusResponse

DESCRIPTOR: _descriptor.FileDescriptor

class SystemSettings(_message.Message):
    __slots__ = ("hardware_settings", "task_settings", "feature_settings", "dream_mode_settings")
    HARDWARE_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    TASK_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    FEATURE_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    DREAM_MODE_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    hardware_settings: _hardware_settings_pb2.HardwareSettings
    task_settings: TaskSettings
    feature_settings: FeatureSettings
    dream_mode_settings: _dream_pb2.DreamModeSettings
    def __init__(self, hardware_settings: _Optional[_Union[_hardware_settings_pb2.HardwareSettings, _Mapping]] = ..., task_settings: _Optional[_Union[TaskSettings, _Mapping]] = ..., feature_settings: _Optional[_Union[FeatureSettings, _Mapping]] = ..., dream_mode_settings: _Optional[_Union[_dream_pb2.DreamModeSettings, _Mapping]] = ...) -> None: ...

class FeatureSettings(_message.Message):
    __slots__ = ("disable_background_agents",)
    DISABLE_BACKGROUND_AGENTS_FIELD_NUMBER: _ClassVar[int]
    disable_background_agents: bool
    def __init__(self, disable_background_agents: bool = ...) -> None: ...

class TaskSettings(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ResetDefaultSettingsRequest(_message.Message):
    __slots__ = ("reset_led_settings",)
    RESET_LED_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    reset_led_settings: bool
    def __init__(self, reset_led_settings: bool = ...) -> None: ...

class ResetDefaultSettingsResponse(_message.Message):
    __slots__ = ("settings",)
    SETTINGS_FIELD_NUMBER: _ClassVar[int]
    settings: SystemSettings
    def __init__(self, settings: _Optional[_Union[SystemSettings, _Mapping]] = ...) -> None: ...
