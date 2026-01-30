from truffle.os import client_metadata_pb2 as _client_metadata_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class UserRecoveryCodes(_message.Message):
    __slots__ = ("codes",)
    CODES_FIELD_NUMBER: _ClassVar[int]
    codes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, codes: _Optional[_Iterable[str]] = ...) -> None: ...

class RegisterNewSessionRequest(_message.Message):
    __slots__ = ("user_id", "metadata", "recovery_code")
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    RECOVERY_CODE_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    metadata: _client_metadata_pb2.ClientMetadata
    recovery_code: str
    def __init__(self, user_id: _Optional[str] = ..., metadata: _Optional[_Union[_client_metadata_pb2.ClientMetadata, _Mapping]] = ..., recovery_code: _Optional[str] = ...) -> None: ...

class RegisterNewSessionResponse(_message.Message):
    __slots__ = ("token", "verifier", "status")
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    VERIFIER_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    token: str
    verifier: _client_metadata_pb2.ClientMetadata
    status: NewSessionStatus
    def __init__(self, token: _Optional[str] = ..., verifier: _Optional[_Union[_client_metadata_pb2.ClientMetadata, _Mapping]] = ..., status: _Optional[_Union[NewSessionStatus, _Mapping]] = ...) -> None: ...

class NewSessionVerification(_message.Message):
    __slots__ = ("verification_token", "expires_at", "requesting_client")
    VERIFICATION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    REQUESTING_CLIENT_FIELD_NUMBER: _ClassVar[int]
    verification_token: str
    expires_at: _timestamp_pb2.Timestamp
    requesting_client: _client_metadata_pb2.ClientMetadata
    def __init__(self, verification_token: _Optional[str] = ..., expires_at: _Optional[_Union[_timestamp_pb2.Timestamp, _Mapping]] = ..., requesting_client: _Optional[_Union[_client_metadata_pb2.ClientMetadata, _Mapping]] = ...) -> None: ...

class VerifyNewSessionRequest(_message.Message):
    __slots__ = ("verification_token", "allow")
    VERIFICATION_TOKEN_FIELD_NUMBER: _ClassVar[int]
    ALLOW_FIELD_NUMBER: _ClassVar[int]
    verification_token: str
    allow: bool
    def __init__(self, verification_token: _Optional[str] = ..., allow: bool = ...) -> None: ...

class NewSessionStatus(_message.Message):
    __slots__ = ("error",)
    class NewSessionError(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        NEW_SESSION_SUCCESS: _ClassVar[NewSessionStatus.NewSessionError]
        NEW_SESSION_TIMEOUT: _ClassVar[NewSessionStatus.NewSessionError]
        NEW_SESSION_REJECTED: _ClassVar[NewSessionStatus.NewSessionError]
        NEW_SESSION_TOKEN_NOT_FOUND: _ClassVar[NewSessionStatus.NewSessionError]
        NEW_SESSION_NO_REQUESTS: _ClassVar[NewSessionStatus.NewSessionError]
    NEW_SESSION_SUCCESS: NewSessionStatus.NewSessionError
    NEW_SESSION_TIMEOUT: NewSessionStatus.NewSessionError
    NEW_SESSION_REJECTED: NewSessionStatus.NewSessionError
    NEW_SESSION_TOKEN_NOT_FOUND: NewSessionStatus.NewSessionError
    NEW_SESSION_NO_REQUESTS: NewSessionStatus.NewSessionError
    ERROR_FIELD_NUMBER: _ClassVar[int]
    error: NewSessionStatus.NewSessionError
    def __init__(self, error: _Optional[_Union[NewSessionStatus.NewSessionError, str]] = ...) -> None: ...
