from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class SystemFactoryResetRequest(_message.Message):
    __slots__ = ("confirmation_code",)
    CONFIRMATION_CODE_FIELD_NUMBER: _ClassVar[int]
    confirmation_code: str
    def __init__(self, confirmation_code: _Optional[str] = ...) -> None: ...

class SystemFactoryResetResponse(_message.Message):
    __slots__ = ("confirmation_code", "reset_initiated")
    CONFIRMATION_CODE_FIELD_NUMBER: _ClassVar[int]
    RESET_INITIATED_FIELD_NUMBER: _ClassVar[int]
    confirmation_code: str
    reset_initiated: bool
    def __init__(self, confirmation_code: _Optional[str] = ..., reset_initiated: bool = ...) -> None: ...

class SystemClearOtherUsersDataRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class SystemClearOtherUsersDataResponse(_message.Message):
    __slots__ = ("num_users_cleared",)
    NUM_USERS_CLEARED_FIELD_NUMBER: _ClassVar[int]
    num_users_cleared: int
    def __init__(self, num_users_cleared: _Optional[int] = ...) -> None: ...
