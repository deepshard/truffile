from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ClientState(_message.Message):
    __slots__ = ("blob",)
    BLOB_FIELD_NUMBER: _ClassVar[int]
    blob: str
    def __init__(self, blob: _Optional[str] = ...) -> None: ...

class UpdateClientStateRequest(_message.Message):
    __slots__ = ("key", "state")
    KEY_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    key: str
    state: ClientState
    def __init__(self, key: _Optional[str] = ..., state: _Optional[_Union[ClientState, _Mapping]] = ...) -> None: ...

class UpdateClientStateResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetClientStateRequest(_message.Message):
    __slots__ = ("key",)
    KEY_FIELD_NUMBER: _ClassVar[int]
    key: str
    def __init__(self, key: _Optional[str] = ...) -> None: ...

class GetClientStateResponse(_message.Message):
    __slots__ = ("state",)
    STATE_FIELD_NUMBER: _ClassVar[int]
    state: ClientState
    def __init__(self, state: _Optional[_Union[ClientState, _Mapping]] = ...) -> None: ...

class GetAllClientStatesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetAllClientStatesResponse(_message.Message):
    __slots__ = ("states",)
    class StatesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: ClientState
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[ClientState, _Mapping]] = ...) -> None: ...
    STATES_FIELD_NUMBER: _ClassVar[int]
    states: _containers.MessageMap[str, ClientState]
    def __init__(self, states: _Optional[_Mapping[str, ClientState]] = ...) -> None: ...
