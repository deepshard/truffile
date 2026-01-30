from truffle.os import hardware_network_pb2 as _hardware_network_pb2
from truffle.common import led_states_pb2 as _led_states_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HardwareInfo(_message.Message):
    __slots__ = ("hostname", "ip_address", "mac_address", "network_status", "current_wifi_network", "serial_number", "start_time")
    HOSTNAME_FIELD_NUMBER: _ClassVar[int]
    IP_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    MAC_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    NETWORK_STATUS_FIELD_NUMBER: _ClassVar[int]
    CURRENT_WIFI_NETWORK_FIELD_NUMBER: _ClassVar[int]
    SERIAL_NUMBER_FIELD_NUMBER: _ClassVar[int]
    START_TIME_FIELD_NUMBER: _ClassVar[int]
    hostname: str
    ip_address: str
    mac_address: str
    network_status: _hardware_network_pb2.HardwareNetworkStatus
    current_wifi_network: _hardware_network_pb2.HardwareWifiNetwork
    serial_number: str
    start_time: _timestamp_pb2.Timestamp
    def __init__(self, hostname: _Optional[str] = ..., ip_address: _Optional[str] = ..., mac_address: _Optional[str] = ..., network_status: _Optional[_Union[_hardware_network_pb2.HardwareNetworkStatus, str]] = ..., current_wifi_network: _Optional[_Union[_hardware_network_pb2.HardwareWifiNetwork, _Mapping]] = ..., serial_number: _Optional[str] = ..., start_time: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
