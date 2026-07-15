import datetime

from truffle.os import client_metadata_pb2 as _client_metadata_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RemoteAccessToken(_message.Message):
    __slots__ = ("device_id", "jwt", "expires_at", "remote_access_address")
    DEVICE_ID_FIELD_NUMBER: _ClassVar[int]
    JWT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    REMOTE_ACCESS_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    device_id: str
    jwt: str
    expires_at: _timestamp_pb2.Timestamp
    remote_access_address: str
    def __init__(self, device_id: _Optional[str] = ..., jwt: _Optional[str] = ..., expires_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., remote_access_address: _Optional[str] = ...) -> None: ...

class NewRemoteAccessTokenRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class NewRemoteAccessTokenResponse(_message.Message):
    __slots__ = ("token",)
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    token: RemoteAccessToken
    def __init__(self, token: _Optional[_Union[RemoteAccessToken, _Mapping]] = ...) -> None: ...

class RemoteAccessStatus(_message.Message):
    __slots__ = ("supported", "healthy", "remote_access_address")
    SUPPORTED_FIELD_NUMBER: _ClassVar[int]
    HEALTHY_FIELD_NUMBER: _ClassVar[int]
    REMOTE_ACCESS_ADDRESS_FIELD_NUMBER: _ClassVar[int]
    supported: bool
    healthy: bool
    remote_access_address: str
    def __init__(self, supported: bool = ..., healthy: bool = ..., remote_access_address: _Optional[str] = ...) -> None: ...

class GetRemoteAccessStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetRemoteAccessStatusResponse(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: RemoteAccessStatus
    def __init__(self, status: _Optional[_Union[RemoteAccessStatus, _Mapping]] = ...) -> None: ...
