from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ClientMetadata(_message.Message):
    __slots__ = ("platform", "version", "device")
    PLATFORM_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    DEVICE_FIELD_NUMBER: _ClassVar[int]
    platform: str
    version: str
    device: str
    def __init__(self, platform: _Optional[str] = ..., version: _Optional[str] = ..., device: _Optional[str] = ...) -> None: ...
