from truffle.os import hardware_network_pb2 as _hardware_network_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HardwareStats(_message.Message):
    __slots__ = ("usage", "temps", "power", "misc", "network_status", "thermal_warning", "disk_warning", "fubar_warning", "current_poll_interval_ms")
    class Usage(_message.Message):
        __slots__ = ("cpu_avg", "cpu_max", "memory_total", "memory_gpu", "memory_cpu", "disk", "gpu", "fan")
        CPU_AVG_FIELD_NUMBER: _ClassVar[int]
        CPU_MAX_FIELD_NUMBER: _ClassVar[int]
        MEMORY_TOTAL_FIELD_NUMBER: _ClassVar[int]
        MEMORY_GPU_FIELD_NUMBER: _ClassVar[int]
        MEMORY_CPU_FIELD_NUMBER: _ClassVar[int]
        DISK_FIELD_NUMBER: _ClassVar[int]
        GPU_FIELD_NUMBER: _ClassVar[int]
        FAN_FIELD_NUMBER: _ClassVar[int]
        cpu_avg: float
        cpu_max: float
        memory_total: float
        memory_gpu: float
        memory_cpu: float
        disk: float
        gpu: float
        fan: float
        def __init__(self, cpu_avg: _Optional[float] = ..., cpu_max: _Optional[float] = ..., memory_total: _Optional[float] = ..., memory_gpu: _Optional[float] = ..., memory_cpu: _Optional[float] = ..., disk: _Optional[float] = ..., gpu: _Optional[float] = ..., fan: _Optional[float] = ...) -> None: ...
    class Temps(_message.Message):
        __slots__ = ("cpu_avg", "cpu_max", "gpu_avg", "gpu_max", "t_max")
        CPU_AVG_FIELD_NUMBER: _ClassVar[int]
        CPU_MAX_FIELD_NUMBER: _ClassVar[int]
        GPU_AVG_FIELD_NUMBER: _ClassVar[int]
        GPU_MAX_FIELD_NUMBER: _ClassVar[int]
        T_MAX_FIELD_NUMBER: _ClassVar[int]
        cpu_avg: float
        cpu_max: float
        gpu_avg: float
        gpu_max: float
        t_max: float
        def __init__(self, cpu_avg: _Optional[float] = ..., cpu_max: _Optional[float] = ..., gpu_avg: _Optional[float] = ..., gpu_max: _Optional[float] = ..., t_max: _Optional[float] = ...) -> None: ...
    class Power(_message.Message):
        __slots__ = ("total", "cpu", "gpu")
        TOTAL_FIELD_NUMBER: _ClassVar[int]
        CPU_FIELD_NUMBER: _ClassVar[int]
        GPU_FIELD_NUMBER: _ClassVar[int]
        total: float
        cpu: float
        gpu: float
        def __init__(self, total: _Optional[float] = ..., cpu: _Optional[float] = ..., gpu: _Optional[float] = ...) -> None: ...
    class Misc(_message.Message):
        __slots__ = ("net_rx", "net_tx", "disk_read", "disk_write")
        NET_RX_FIELD_NUMBER: _ClassVar[int]
        NET_TX_FIELD_NUMBER: _ClassVar[int]
        DISK_READ_FIELD_NUMBER: _ClassVar[int]
        DISK_WRITE_FIELD_NUMBER: _ClassVar[int]
        net_rx: int
        net_tx: int
        disk_read: int
        disk_write: int
        def __init__(self, net_rx: _Optional[int] = ..., net_tx: _Optional[int] = ..., disk_read: _Optional[int] = ..., disk_write: _Optional[int] = ...) -> None: ...
    USAGE_FIELD_NUMBER: _ClassVar[int]
    TEMPS_FIELD_NUMBER: _ClassVar[int]
    POWER_FIELD_NUMBER: _ClassVar[int]
    MISC_FIELD_NUMBER: _ClassVar[int]
    NETWORK_STATUS_FIELD_NUMBER: _ClassVar[int]
    THERMAL_WARNING_FIELD_NUMBER: _ClassVar[int]
    DISK_WARNING_FIELD_NUMBER: _ClassVar[int]
    FUBAR_WARNING_FIELD_NUMBER: _ClassVar[int]
    CURRENT_POLL_INTERVAL_MS_FIELD_NUMBER: _ClassVar[int]
    usage: HardwareStats.Usage
    temps: HardwareStats.Temps
    power: HardwareStats.Power
    misc: HardwareStats.Misc
    network_status: _hardware_network_pb2.HardwareNetworkStatus
    thermal_warning: bool
    disk_warning: bool
    fubar_warning: bool
    current_poll_interval_ms: int
    def __init__(self, usage: _Optional[_Union[HardwareStats.Usage, _Mapping]] = ..., temps: _Optional[_Union[HardwareStats.Temps, _Mapping]] = ..., power: _Optional[_Union[HardwareStats.Power, _Mapping]] = ..., misc: _Optional[_Union[HardwareStats.Misc, _Mapping]] = ..., network_status: _Optional[_Union[_hardware_network_pb2.HardwareNetworkStatus, str]] = ..., thermal_warning: bool = ..., disk_warning: bool = ..., fubar_warning: bool = ..., current_poll_interval_ms: _Optional[int] = ...) -> None: ...

class HardwareStatsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
