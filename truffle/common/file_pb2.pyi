from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FileMetadata(_message.Message):
    __slots__ = ("name", "mime_type", "size")
    NAME_FIELD_NUMBER: _ClassVar[int]
    MIME_TYPE_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    name: str
    mime_type: str
    size: int
    def __init__(self, name: _Optional[str] = ..., mime_type: _Optional[str] = ..., size: _Optional[int] = ...) -> None: ...

class AttachedFile(_message.Message):
    __slots__ = ("path", "metadata")
    PATH_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    path: str
    metadata: FileMetadata
    def __init__(self, path: _Optional[str] = ..., metadata: _Optional[_Union[FileMetadata, _Mapping]] = ...) -> None: ...

class AttachedFileIntent(_message.Message):
    __slots__ = ("file",)
    FILE_FIELD_NUMBER: _ClassVar[int]
    file: AttachedFile
    def __init__(self, file: _Optional[_Union[AttachedFile, _Mapping]] = ...) -> None: ...
