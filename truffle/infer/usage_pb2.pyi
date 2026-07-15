from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Usage(_message.Message):
    __slots__ = ("total_time", "prefill_time", "decode_time", "ttft", "inter_token_latency", "decode_tps", "prefill_tps", "tokens")
    class Tokens(_message.Message):
        __slots__ = ("prompt", "completion", "prefill", "decode", "jump_forward", "image")
        PROMPT_FIELD_NUMBER: _ClassVar[int]
        COMPLETION_FIELD_NUMBER: _ClassVar[int]
        PREFILL_FIELD_NUMBER: _ClassVar[int]
        DECODE_FIELD_NUMBER: _ClassVar[int]
        JUMP_FORWARD_FIELD_NUMBER: _ClassVar[int]
        IMAGE_FIELD_NUMBER: _ClassVar[int]
        prompt: int
        completion: int
        prefill: int
        decode: int
        jump_forward: int
        image: int
        def __init__(self, prompt: _Optional[int] = ..., completion: _Optional[int] = ..., prefill: _Optional[int] = ..., decode: _Optional[int] = ..., jump_forward: _Optional[int] = ..., image: _Optional[int] = ...) -> None: ...
    TOTAL_TIME_FIELD_NUMBER: _ClassVar[int]
    PREFILL_TIME_FIELD_NUMBER: _ClassVar[int]
    DECODE_TIME_FIELD_NUMBER: _ClassVar[int]
    TTFT_FIELD_NUMBER: _ClassVar[int]
    INTER_TOKEN_LATENCY_FIELD_NUMBER: _ClassVar[int]
    DECODE_TPS_FIELD_NUMBER: _ClassVar[int]
    PREFILL_TPS_FIELD_NUMBER: _ClassVar[int]
    TOKENS_FIELD_NUMBER: _ClassVar[int]
    total_time: float
    prefill_time: float
    decode_time: float
    ttft: float
    inter_token_latency: float
    decode_tps: float
    prefill_tps: float
    tokens: Usage.Tokens
    def __init__(self, total_time: _Optional[float] = ..., prefill_time: _Optional[float] = ..., decode_time: _Optional[float] = ..., ttft: _Optional[float] = ..., inter_token_latency: _Optional[float] = ..., decode_tps: _Optional[float] = ..., prefill_tps: _Optional[float] = ..., tokens: _Optional[_Union[Usage.Tokens, _Mapping]] = ...) -> None: ...

class SystemUsage(_message.Message):
    __slots__ = ("device_name", "total_memory", "available_memory")
    DEVICE_NAME_FIELD_NUMBER: _ClassVar[int]
    TOTAL_MEMORY_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_MEMORY_FIELD_NUMBER: _ClassVar[int]
    device_name: str
    total_memory: int
    available_memory: int
    def __init__(self, device_name: _Optional[str] = ..., total_memory: _Optional[int] = ..., available_memory: _Optional[int] = ...) -> None: ...
