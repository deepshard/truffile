from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class EmbeddingModelInfo(_message.Message):
    __slots__ = ("id", "name", "version", "config", "uuid")
    class Config(_message.Message):
        __slots__ = ("max_input_length", "max_batch_size", "embedding_dim")
        MAX_INPUT_LENGTH_FIELD_NUMBER: _ClassVar[int]
        MAX_BATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
        EMBEDDING_DIM_FIELD_NUMBER: _ClassVar[int]
        max_input_length: int
        max_batch_size: int
        embedding_dim: int
        def __init__(self, max_input_length: _Optional[int] = ..., max_batch_size: _Optional[int] = ..., embedding_dim: _Optional[int] = ...) -> None: ...
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    UUID_FIELD_NUMBER: _ClassVar[int]
    id: int
    name: str
    version: str
    config: EmbeddingModelInfo.Config
    uuid: str
    def __init__(self, id: _Optional[int] = ..., name: _Optional[str] = ..., version: _Optional[str] = ..., config: _Optional[_Union[EmbeddingModelInfo.Config, _Mapping]] = ..., uuid: _Optional[str] = ...) -> None: ...

class EmbeddingModelList(_message.Message):
    __slots__ = ("models",)
    MODELS_FIELD_NUMBER: _ClassVar[int]
    models: _containers.RepeatedCompositeFieldContainer[EmbeddingModelInfo]
    def __init__(self, models: _Optional[_Iterable[_Union[EmbeddingModelInfo, _Mapping]]] = ...) -> None: ...

class ModelConfig(_message.Message):
    __slots__ = ("info", "context_length", "max_batch_size", "data_type", "loaded")
    class ModelConfigInfo(_message.Message):
        __slots__ = ("context_length_limit_max", "context_length_limit_min", "model_context_length", "batch_size_limit_max", "batch_size_limit_min", "has_chain_of_thought", "is_agentic", "memory_usage_params", "memory_usage_inference", "available_data_types")
        CONTEXT_LENGTH_LIMIT_MAX_FIELD_NUMBER: _ClassVar[int]
        CONTEXT_LENGTH_LIMIT_MIN_FIELD_NUMBER: _ClassVar[int]
        MODEL_CONTEXT_LENGTH_FIELD_NUMBER: _ClassVar[int]
        BATCH_SIZE_LIMIT_MAX_FIELD_NUMBER: _ClassVar[int]
        BATCH_SIZE_LIMIT_MIN_FIELD_NUMBER: _ClassVar[int]
        HAS_CHAIN_OF_THOUGHT_FIELD_NUMBER: _ClassVar[int]
        IS_AGENTIC_FIELD_NUMBER: _ClassVar[int]
        MEMORY_USAGE_PARAMS_FIELD_NUMBER: _ClassVar[int]
        MEMORY_USAGE_INFERENCE_FIELD_NUMBER: _ClassVar[int]
        AVAILABLE_DATA_TYPES_FIELD_NUMBER: _ClassVar[int]
        context_length_limit_max: int
        context_length_limit_min: int
        model_context_length: int
        batch_size_limit_max: int
        batch_size_limit_min: int
        has_chain_of_thought: bool
        is_agentic: bool
        memory_usage_params: int
        memory_usage_inference: int
        available_data_types: _containers.RepeatedScalarFieldContainer[str]
        def __init__(self, context_length_limit_max: _Optional[int] = ..., context_length_limit_min: _Optional[int] = ..., model_context_length: _Optional[int] = ..., batch_size_limit_max: _Optional[int] = ..., batch_size_limit_min: _Optional[int] = ..., has_chain_of_thought: bool = ..., is_agentic: bool = ..., memory_usage_params: _Optional[int] = ..., memory_usage_inference: _Optional[int] = ..., available_data_types: _Optional[_Iterable[str]] = ...) -> None: ...
    INFO_FIELD_NUMBER: _ClassVar[int]
    CONTEXT_LENGTH_FIELD_NUMBER: _ClassVar[int]
    MAX_BATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
    DATA_TYPE_FIELD_NUMBER: _ClassVar[int]
    LOADED_FIELD_NUMBER: _ClassVar[int]
    info: ModelConfig.ModelConfigInfo
    context_length: int
    max_batch_size: int
    data_type: str
    loaded: bool
    def __init__(self, info: _Optional[_Union[ModelConfig.ModelConfigInfo, _Mapping]] = ..., context_length: _Optional[int] = ..., max_batch_size: _Optional[int] = ..., data_type: _Optional[str] = ..., loaded: bool = ...) -> None: ...

class Model(_message.Message):
    __slots__ = ("uuid", "name", "provider", "config", "state")
    class ModelState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        MODEL_STATE_INVALID: _ClassVar[Model.ModelState]
        MODEL_STATE_AVAILABLE: _ClassVar[Model.ModelState]
        MODEL_STATE_LOADING: _ClassVar[Model.ModelState]
        MODEL_STATE_UNLOADING: _ClassVar[Model.ModelState]
        MODEL_STATE_LOADED: _ClassVar[Model.ModelState]
    MODEL_STATE_INVALID: Model.ModelState
    MODEL_STATE_AVAILABLE: Model.ModelState
    MODEL_STATE_LOADING: Model.ModelState
    MODEL_STATE_UNLOADING: Model.ModelState
    MODEL_STATE_LOADED: Model.ModelState
    UUID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    CONFIG_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    uuid: str
    name: str
    provider: str
    config: ModelConfig
    state: Model.ModelState
    def __init__(self, uuid: _Optional[str] = ..., name: _Optional[str] = ..., provider: _Optional[str] = ..., config: _Optional[_Union[ModelConfig, _Mapping]] = ..., state: _Optional[_Union[Model.ModelState, str]] = ...) -> None: ...

class ModelStateUpdate(_message.Message):
    __slots__ = ("model_uuid", "state", "progress")
    MODEL_UUID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    PROGRESS_FIELD_NUMBER: _ClassVar[int]
    model_uuid: str
    state: Model.ModelState
    progress: int
    def __init__(self, model_uuid: _Optional[str] = ..., state: _Optional[_Union[Model.ModelState, str]] = ..., progress: _Optional[int] = ...) -> None: ...

class ModelList(_message.Message):
    __slots__ = ("models", "total_memory", "used_memory")
    MODELS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_MEMORY_FIELD_NUMBER: _ClassVar[int]
    USED_MEMORY_FIELD_NUMBER: _ClassVar[int]
    models: _containers.RepeatedCompositeFieldContainer[Model]
    total_memory: int
    used_memory: int
    def __init__(self, models: _Optional[_Iterable[_Union[Model, _Mapping]]] = ..., total_memory: _Optional[int] = ..., used_memory: _Optional[int] = ...) -> None: ...

class GetModelRequest(_message.Message):
    __slots__ = ("model_uuid",)
    MODEL_UUID_FIELD_NUMBER: _ClassVar[int]
    model_uuid: str
    def __init__(self, model_uuid: _Optional[str] = ...) -> None: ...

class GetModelListRequest(_message.Message):
    __slots__ = ("use_filter", "available", "loaded", "agentic")
    USE_FILTER_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    LOADED_FIELD_NUMBER: _ClassVar[int]
    AGENTIC_FIELD_NUMBER: _ClassVar[int]
    use_filter: bool
    available: bool
    loaded: bool
    agentic: bool
    def __init__(self, use_filter: bool = ..., available: bool = ..., loaded: bool = ..., agentic: bool = ...) -> None: ...

class SetModelsResponse(_message.Message):
    __slots__ = ("code", "message", "updated_list")
    class SetModelsErrorCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        OK: _ClassVar[SetModelsResponse.SetModelsErrorCode]
        INVALID_CONFIG: _ClassVar[SetModelsResponse.SetModelsErrorCode]
        NOT_ENOUGH_MEMORY: _ClassVar[SetModelsResponse.SetModelsErrorCode]
        MODEL_IN_USE: _ClassVar[SetModelsResponse.SetModelsErrorCode]
    OK: SetModelsResponse.SetModelsErrorCode
    INVALID_CONFIG: SetModelsResponse.SetModelsErrorCode
    NOT_ENOUGH_MEMORY: SetModelsResponse.SetModelsErrorCode
    MODEL_IN_USE: SetModelsResponse.SetModelsErrorCode
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    UPDATED_LIST_FIELD_NUMBER: _ClassVar[int]
    code: SetModelsResponse.SetModelsErrorCode
    message: str
    updated_list: ModelList
    def __init__(self, code: _Optional[_Union[SetModelsResponse.SetModelsErrorCode, str]] = ..., message: _Optional[str] = ..., updated_list: _Optional[_Union[ModelList, _Mapping]] = ...) -> None: ...

class SetModelsRequest(_message.Message):
    __slots__ = ("updates",)
    class UpdatesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: ModelConfig
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[ModelConfig, _Mapping]] = ...) -> None: ...
    UPDATES_FIELD_NUMBER: _ClassVar[int]
    updates: _containers.MessageMap[str, ModelConfig]
    def __init__(self, updates: _Optional[_Mapping[str, ModelConfig]] = ...) -> None: ...
