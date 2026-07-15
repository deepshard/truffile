from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HardwareSettings(_message.Message):
    __slots__ = ("truffle_name", "led_settings")
    class LEDSettings(_message.Message):
        __slots__ = ("enabled", "brightness")
        ENABLED_FIELD_NUMBER: _ClassVar[int]
        BRIGHTNESS_FIELD_NUMBER: _ClassVar[int]
        enabled: bool
        brightness: float
        def __init__(self, enabled: bool = ..., brightness: _Optional[float] = ...) -> None: ...
    TRUFFLE_NAME_FIELD_NUMBER: _ClassVar[int]
    LED_SETTINGS_FIELD_NUMBER: _ClassVar[int]
    truffle_name: str
    led_settings: HardwareSettings.LEDSettings
    def __init__(self, truffle_name: _Optional[str] = ..., led_settings: _Optional[_Union[HardwareSettings.LEDSettings, _Mapping]] = ...) -> None: ...
