from truffle.os import task_user_response_pb2 as _task_user_response_pb2
from truffle.common import content_pb2 as _content_pb2
from truffle.infer import usage_pb2 as _usage_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union
from truffle.common.content_pb2 import MediaSource as MediaSource
from truffle.common.content_pb2 import WebComponent as WebComponent

DESCRIPTOR: _descriptor.FileDescriptor

class Step(_message.Message):
    __slots__ = ("state", "user_response", "thinking", "tool_calls", "execution", "results", "metrics", "model_uuid")
    class StepState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        STEP_INVALID: _ClassVar[Step.StepState]
        STEP_GENERATING: _ClassVar[Step.StepState]
        STEP_EXECUTING: _ClassVar[Step.StepState]
        STEP_RESULT: _ClassVar[Step.StepState]
    STEP_INVALID: Step.StepState
    STEP_GENERATING: Step.StepState
    STEP_EXECUTING: Step.StepState
    STEP_RESULT: Step.StepState
    class Thinking(_message.Message):
        __slots__ = ("cot_chunks", "cot_summaries", "raw_output", "thinking_finished")
        COT_CHUNKS_FIELD_NUMBER: _ClassVar[int]
        COT_SUMMARIES_FIELD_NUMBER: _ClassVar[int]
        RAW_OUTPUT_FIELD_NUMBER: _ClassVar[int]
        THINKING_FINISHED_FIELD_NUMBER: _ClassVar[int]
        cot_chunks: _containers.RepeatedScalarFieldContainer[str]
        cot_summaries: _containers.RepeatedScalarFieldContainer[str]
        raw_output: str
        thinking_finished: bool
        def __init__(self, cot_chunks: _Optional[_Iterable[str]] = ..., cot_summaries: _Optional[_Iterable[str]] = ..., raw_output: _Optional[str] = ..., thinking_finished: bool = ...) -> None: ...
    class ToolCall(_message.Message):
        __slots__ = ("tool_name", "summary")
        TOOL_NAME_FIELD_NUMBER: _ClassVar[int]
        SUMMARY_FIELD_NUMBER: _ClassVar[int]
        tool_name: str
        summary: str
        def __init__(self, tool_name: _Optional[str] = ..., summary: _Optional[str] = ...) -> None: ...
    class Execute(_message.Message):
        __slots__ = ("tool_updates",)
        TOOL_UPDATES_FIELD_NUMBER: _ClassVar[int]
        tool_updates: _containers.RepeatedScalarFieldContainer[str]
        def __init__(self, tool_updates: _Optional[_Iterable[str]] = ...) -> None: ...
    class Results(_message.Message):
        __slots__ = ("summary", "content", "content_incomplete", "web")
        SUMMARY_FIELD_NUMBER: _ClassVar[int]
        CONTENT_FIELD_NUMBER: _ClassVar[int]
        CONTENT_INCOMPLETE_FIELD_NUMBER: _ClassVar[int]
        WEB_FIELD_NUMBER: _ClassVar[int]
        summary: str
        content: str
        content_incomplete: bool
        web: _content_pb2.WebComponent
        def __init__(self, summary: _Optional[str] = ..., content: _Optional[str] = ..., content_incomplete: bool = ..., web: _Optional[_Union[_content_pb2.WebComponent, _Mapping]] = ...) -> None: ...
    class Metrics(_message.Message):
        __slots__ = ("inference_usage",)
        INFERENCE_USAGE_FIELD_NUMBER: _ClassVar[int]
        inference_usage: _usage_pb2.Usage
        def __init__(self, inference_usage: _Optional[_Union[_usage_pb2.Usage, _Mapping]] = ...) -> None: ...
    STATE_FIELD_NUMBER: _ClassVar[int]
    USER_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    THINKING_FIELD_NUMBER: _ClassVar[int]
    TOOL_CALLS_FIELD_NUMBER: _ClassVar[int]
    EXECUTION_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    METRICS_FIELD_NUMBER: _ClassVar[int]
    MODEL_UUID_FIELD_NUMBER: _ClassVar[int]
    state: Step.StepState
    user_response: _task_user_response_pb2.PendingUserResponse
    thinking: Step.Thinking
    tool_calls: _containers.RepeatedCompositeFieldContainer[Step.ToolCall]
    execution: Step.Execute
    results: Step.Results
    metrics: Step.Metrics
    model_uuid: str
    def __init__(self, state: _Optional[_Union[Step.StepState, str]] = ..., user_response: _Optional[_Union[_task_user_response_pb2.PendingUserResponse, _Mapping]] = ..., thinking: _Optional[_Union[Step.Thinking, _Mapping]] = ..., tool_calls: _Optional[_Iterable[_Union[Step.ToolCall, _Mapping]]] = ..., execution: _Optional[_Union[Step.Execute, _Mapping]] = ..., results: _Optional[_Union[Step.Results, _Mapping]] = ..., metrics: _Optional[_Union[Step.Metrics, _Mapping]] = ..., model_uuid: _Optional[str] = ...) -> None: ...
