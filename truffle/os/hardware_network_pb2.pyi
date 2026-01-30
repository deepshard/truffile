from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class HardwareNetworkStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    NET_DEFAULT: _ClassVar[HardwareNetworkStatus]
    NET_NOT_CONNECTED: _ClassVar[HardwareNetworkStatus]
    NET_NO_INTERNET: _ClassVar[HardwareNetworkStatus]
    NET_CONNECTED: _ClassVar[HardwareNetworkStatus]
NET_DEFAULT: HardwareNetworkStatus
NET_NOT_CONNECTED: HardwareNetworkStatus
NET_NO_INTERNET: HardwareNetworkStatus
NET_CONNECTED: HardwareNetworkStatus

class HardwareWifiNetwork(_message.Message):
    __slots__ = ("ssid", "rssi")
    SSID_FIELD_NUMBER: _ClassVar[int]
    RSSI_FIELD_NUMBER: _ClassVar[int]
    ssid: str
    rssi: float
    def __init__(self, ssid: _Optional[str] = ..., rssi: _Optional[float] = ...) -> None: ...
