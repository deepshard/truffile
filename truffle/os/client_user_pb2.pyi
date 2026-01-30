from truffle.os import client_metadata_pb2 as _client_metadata_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RegisterNewUserRequest(_message.Message):
    __slots__ = ("metadata", "user_id")
    METADATA_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    metadata: _client_metadata_pb2.ClientMetadata
    user_id: str
    def __init__(self, metadata: _Optional[_Union[_client_metadata_pb2.ClientMetadata, _Mapping]] = ..., user_id: _Optional[str] = ...) -> None: ...

class RegisterNewUserResponse(_message.Message):
    __slots__ = ("user_id", "token")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    token: str
    def __init__(self, user_id: _Optional[str] = ..., token: _Optional[str] = ...) -> None: ...

class UserIDForTokenRequest(_message.Message):
    __slots__ = ("token",)
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    token: str
    def __init__(self, token: _Optional[str] = ...) -> None: ...

class UserIDForTokenResponse(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    def __init__(self, user_id: _Optional[str] = ...) -> None: ...
