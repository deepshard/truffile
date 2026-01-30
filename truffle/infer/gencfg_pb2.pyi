from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ResponseFormat(_message.Message):
    __slots__ = ("format", "schema", "experimental")
    class Format(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        TEXT: _ClassVar[ResponseFormat.Format]
        JSON: _ClassVar[ResponseFormat.Format]
        EBNF: _ClassVar[ResponseFormat.Format]
        STRUCTURAL_TAG: _ClassVar[ResponseFormat.Format]
    TEXT: ResponseFormat.Format
    JSON: ResponseFormat.Format
    EBNF: ResponseFormat.Format
    STRUCTURAL_TAG: ResponseFormat.Format
    class Experimental(_message.Message):
        __slots__ = ("additional_ebnf", "old_root_key", "new_root_key")
        ADDITIONAL_EBNF_FIELD_NUMBER: _ClassVar[int]
        OLD_ROOT_KEY_FIELD_NUMBER: _ClassVar[int]
        NEW_ROOT_KEY_FIELD_NUMBER: _ClassVar[int]
        additional_ebnf: str
        old_root_key: str
        new_root_key: str
        def __init__(self, additional_ebnf: _Optional[str] = ..., old_root_key: _Optional[str] = ..., new_root_key: _Optional[str] = ...) -> None: ...
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_FIELD_NUMBER: _ClassVar[int]
    EXPERIMENTAL_FIELD_NUMBER: _ClassVar[int]
    format: ResponseFormat.Format
    schema: str
    experimental: ResponseFormat.Experimental
    def __init__(self, format: _Optional[_Union[ResponseFormat.Format, str]] = ..., schema: _Optional[str] = ..., experimental: _Optional[_Union[ResponseFormat.Experimental, _Mapping]] = ...) -> None: ...

class GenerationConfig(_message.Message):
    __slots__ = ("temp", "top_p", "freq_penalty", "pres_penalty", "rep_penalty", "seed", "max_tokens", "stop_strs", "stop_ids", "response_format", "debug")
    class Debug(_message.Message):
        __slots__ = ("ignore_eos", "pinned_context")
        IGNORE_EOS_FIELD_NUMBER: _ClassVar[int]
        PINNED_CONTEXT_FIELD_NUMBER: _ClassVar[int]
        ignore_eos: bool
        pinned_context: bool
        def __init__(self, ignore_eos: bool = ..., pinned_context: bool = ...) -> None: ...
    TEMP_FIELD_NUMBER: _ClassVar[int]
    TOP_P_FIELD_NUMBER: _ClassVar[int]
    FREQ_PENALTY_FIELD_NUMBER: _ClassVar[int]
    PRES_PENALTY_FIELD_NUMBER: _ClassVar[int]
    REP_PENALTY_FIELD_NUMBER: _ClassVar[int]
    SEED_FIELD_NUMBER: _ClassVar[int]
    MAX_TOKENS_FIELD_NUMBER: _ClassVar[int]
    STOP_STRS_FIELD_NUMBER: _ClassVar[int]
    STOP_IDS_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_FORMAT_FIELD_NUMBER: _ClassVar[int]
    DEBUG_FIELD_NUMBER: _ClassVar[int]
    temp: float
    top_p: float
    freq_penalty: float
    pres_penalty: float
    rep_penalty: float
    seed: int
    max_tokens: int
    stop_strs: _containers.RepeatedScalarFieldContainer[str]
    stop_ids: _containers.RepeatedScalarFieldContainer[int]
    response_format: ResponseFormat
    debug: GenerationConfig.Debug
    def __init__(self, temp: _Optional[float] = ..., top_p: _Optional[float] = ..., freq_penalty: _Optional[float] = ..., pres_penalty: _Optional[float] = ..., rep_penalty: _Optional[float] = ..., seed: _Optional[int] = ..., max_tokens: _Optional[int] = ..., stop_strs: _Optional[_Iterable[str]] = ..., stop_ids: _Optional[_Iterable[int]] = ..., response_format: _Optional[_Union[ResponseFormat, _Mapping]] = ..., debug: _Optional[_Union[GenerationConfig.Debug, _Mapping]] = ...) -> None: ...

class ValidateConfigRequest(_message.Message):
    __slots__ = ("cfg", "model_uuid")
    CFG_FIELD_NUMBER: _ClassVar[int]
    MODEL_UUID_FIELD_NUMBER: _ClassVar[int]
    cfg: GenerationConfig
    model_uuid: str
    def __init__(self, cfg: _Optional[_Union[GenerationConfig, _Mapping]] = ..., model_uuid: _Optional[str] = ...) -> None: ...

class ValidateConfigResponse(_message.Message):
    __slots__ = ("valid", "error", "warnings")
    VALID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    WARNINGS_FIELD_NUMBER: _ClassVar[int]
    valid: bool
    error: str
    warnings: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, valid: bool = ..., error: _Optional[str] = ..., warnings: _Optional[_Iterable[str]] = ...) -> None: ...
