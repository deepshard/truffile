import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from truffle.os import convo_pb2 as _convo_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MemorySource(_message.Message):
    __slots__ = ("convo_node_ref", "user_provided")
    CONVO_NODE_REF_FIELD_NUMBER: _ClassVar[int]
    USER_PROVIDED_FIELD_NUMBER: _ClassVar[int]
    convo_node_ref: _convo_pb2.ConvoNodeRef
    user_provided: _timestamp_pb2.Timestamp
    def __init__(self, convo_node_ref: _Optional[_Union[_convo_pb2.ConvoNodeRef, _Mapping]] = ..., user_provided: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class Memory(_message.Message):
    __slots__ = ("memory_id", "content", "tags", "created_at", "updated_at", "source", "extra", "title")
    MEMORY_ID_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    EXTRA_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    memory_id: str
    content: str
    tags: _containers.RepeatedScalarFieldContainer[str]
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    source: MemorySource
    extra: _struct_pb2.Struct
    title: str
    def __init__(self, memory_id: _Optional[str] = ..., content: _Optional[str] = ..., tags: _Optional[_Iterable[str]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., source: _Optional[_Union[MemorySource, _Mapping]] = ..., extra: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., title: _Optional[str] = ...) -> None: ...

class MemoryGetRequest(_message.Message):
    __slots__ = ("memory_id", "page_size", "page_token", "tags_to_include")
    MEMORY_ID_FIELD_NUMBER: _ClassVar[int]
    PAGE_SIZE_FIELD_NUMBER: _ClassVar[int]
    PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    TAGS_TO_INCLUDE_FIELD_NUMBER: _ClassVar[int]
    memory_id: str
    page_size: int
    page_token: str
    tags_to_include: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, memory_id: _Optional[str] = ..., page_size: _Optional[int] = ..., page_token: _Optional[str] = ..., tags_to_include: _Optional[_Iterable[str]] = ...) -> None: ...

class MemoryGetResponse(_message.Message):
    __slots__ = ("memories", "next_page_token")
    MEMORIES_FIELD_NUMBER: _ClassVar[int]
    NEXT_PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    memories: _containers.RepeatedCompositeFieldContainer[Memory]
    next_page_token: str
    def __init__(self, memories: _Optional[_Iterable[_Union[Memory, _Mapping]]] = ..., next_page_token: _Optional[str] = ...) -> None: ...

class MemorySearchRequest(_message.Message):
    __slots__ = ("query", "page_size", "page_token", "tags_to_include", "created_after", "created_before")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    PAGE_SIZE_FIELD_NUMBER: _ClassVar[int]
    PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    TAGS_TO_INCLUDE_FIELD_NUMBER: _ClassVar[int]
    CREATED_AFTER_FIELD_NUMBER: _ClassVar[int]
    CREATED_BEFORE_FIELD_NUMBER: _ClassVar[int]
    query: str
    page_size: int
    page_token: str
    tags_to_include: _containers.RepeatedScalarFieldContainer[str]
    created_after: _timestamp_pb2.Timestamp
    created_before: _timestamp_pb2.Timestamp
    def __init__(self, query: _Optional[str] = ..., page_size: _Optional[int] = ..., page_token: _Optional[str] = ..., tags_to_include: _Optional[_Iterable[str]] = ..., created_after: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., created_before: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class MemorySearchResponse(_message.Message):
    __slots__ = ("memories", "next_page_token")
    MEMORIES_FIELD_NUMBER: _ClassVar[int]
    NEXT_PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    memories: _containers.RepeatedCompositeFieldContainer[Memory]
    next_page_token: str
    def __init__(self, memories: _Optional[_Iterable[_Union[Memory, _Mapping]]] = ..., next_page_token: _Optional[str] = ...) -> None: ...

class MemoryUpsertRequest(_message.Message):
    __slots__ = ("memory_id", "content", "tags", "title")
    MEMORY_ID_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    memory_id: str
    content: str
    tags: _containers.RepeatedScalarFieldContainer[str]
    title: str
    def __init__(self, memory_id: _Optional[str] = ..., content: _Optional[str] = ..., tags: _Optional[_Iterable[str]] = ..., title: _Optional[str] = ...) -> None: ...

class MemoryUpsertResponse(_message.Message):
    __slots__ = ("memory",)
    MEMORY_FIELD_NUMBER: _ClassVar[int]
    memory: Memory
    def __init__(self, memory: _Optional[_Union[Memory, _Mapping]] = ...) -> None: ...

class MemoryDeleteRequest(_message.Message):
    __slots__ = ("memory_id",)
    MEMORY_ID_FIELD_NUMBER: _ClassVar[int]
    memory_id: str
    def __init__(self, memory_id: _Optional[str] = ...) -> None: ...

class MemoryDeleteResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class UserProfile(_message.Message):
    __slots__ = ("content", "updated_at")
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    content: str
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, content: _Optional[str] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class UserCustomInstructions(_message.Message):
    __slots__ = ("content", "updated_at")
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    content: str
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, content: _Optional[str] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class MemoryGetUserProfileRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class MemoryGetUserProfileResponse(_message.Message):
    __slots__ = ("profile", "custom_instructions")
    PROFILE_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_INSTRUCTIONS_FIELD_NUMBER: _ClassVar[int]
    profile: UserProfile
    custom_instructions: UserCustomInstructions
    def __init__(self, profile: _Optional[_Union[UserProfile, _Mapping]] = ..., custom_instructions: _Optional[_Union[UserCustomInstructions, _Mapping]] = ...) -> None: ...

class MemorySetUserProfileRequest(_message.Message):
    __slots__ = ("content", "custom_instructions", "profile")
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_INSTRUCTIONS_FIELD_NUMBER: _ClassVar[int]
    PROFILE_FIELD_NUMBER: _ClassVar[int]
    content: str
    custom_instructions: UserCustomInstructions
    profile: UserProfile
    def __init__(self, content: _Optional[str] = ..., custom_instructions: _Optional[_Union[UserCustomInstructions, _Mapping]] = ..., profile: _Optional[_Union[UserProfile, _Mapping]] = ...) -> None: ...

class MemorySetUserProfileResponse(_message.Message):
    __slots__ = ("profile", "custom_instructions")
    PROFILE_FIELD_NUMBER: _ClassVar[int]
    CUSTOM_INSTRUCTIONS_FIELD_NUMBER: _ClassVar[int]
    profile: UserProfile
    custom_instructions: UserCustomInstructions
    def __init__(self, profile: _Optional[_Union[UserProfile, _Mapping]] = ..., custom_instructions: _Optional[_Union[UserCustomInstructions, _Mapping]] = ...) -> None: ...

class MemoryUpdateTagsRequest(_message.Message):
    __slots__ = ("memory_ids", "add_tags", "remove_tags")
    MEMORY_IDS_FIELD_NUMBER: _ClassVar[int]
    ADD_TAGS_FIELD_NUMBER: _ClassVar[int]
    REMOVE_TAGS_FIELD_NUMBER: _ClassVar[int]
    memory_ids: _containers.RepeatedScalarFieldContainer[str]
    add_tags: _containers.RepeatedScalarFieldContainer[str]
    remove_tags: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, memory_ids: _Optional[_Iterable[str]] = ..., add_tags: _Optional[_Iterable[str]] = ..., remove_tags: _Optional[_Iterable[str]] = ...) -> None: ...

class MemoryUpdateTagsResponse(_message.Message):
    __slots__ = ("memories",)
    MEMORIES_FIELD_NUMBER: _ClassVar[int]
    memories: _containers.RepeatedCompositeFieldContainer[Memory]
    def __init__(self, memories: _Optional[_Iterable[_Union[Memory, _Mapping]]] = ...) -> None: ...

class MemoryTag(_message.Message):
    __slots__ = ("name", "count")
    NAME_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    name: str
    count: int
    def __init__(self, name: _Optional[str] = ..., count: _Optional[int] = ...) -> None: ...

class MemoryListAllTagsRequest(_message.Message):
    __slots__ = ("query", "page_size", "page_token")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    PAGE_SIZE_FIELD_NUMBER: _ClassVar[int]
    PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    query: str
    page_size: int
    page_token: str
    def __init__(self, query: _Optional[str] = ..., page_size: _Optional[int] = ..., page_token: _Optional[str] = ...) -> None: ...

class MemoryListAllTagsResponse(_message.Message):
    __slots__ = ("tags", "page_token")
    TAGS_FIELD_NUMBER: _ClassVar[int]
    PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    tags: _containers.RepeatedCompositeFieldContainer[MemoryTag]
    page_token: str
    def __init__(self, tags: _Optional[_Iterable[_Union[MemoryTag, _Mapping]]] = ..., page_token: _Optional[str] = ...) -> None: ...
