from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import empty_pb2 as _empty_pb2
from truffle.os import hardware_stats_pb2 as _hardware_stats_pb2
from truffle.os import client_session_pb2 as _client_session_pb2
from truffle.app import background_pb2 as _background_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SubscribeToNotificationsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class Notification(_message.Message):
    __slots__ = ("type", "associated_id", "none", "payload", "new_session_verification", "background_app_notification", "is_error")
    class NotificationType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        NOTIFICATION_TYPE_INVALID: _ClassVar[Notification.NotificationType]
        BG_FEED_UPDATE: _ClassVar[Notification.NotificationType]
        TASK_HAS_RESULT: _ClassVar[Notification.NotificationType]
        BG_FEED_FEEDBACK_PROCESSED: _ClassVar[Notification.NotificationType]
        BG_APP_LIST_DIRTY: _ClassVar[Notification.NotificationType]
        FG_APP_LIST_DIRTY: _ClassVar[Notification.NotificationType]
        TASK_LIST_DIRTY: _ClassVar[Notification.NotificationType]
        SESSION_READY: _ClassVar[Notification.NotificationType]
        SESSION_VERIFICATION_REQUEST: _ClassVar[Notification.NotificationType]
        SESSION_ADDED: _ClassVar[Notification.NotificationType]
        SESSION_DENIED: _ClassVar[Notification.NotificationType]
        SERVER_CLOSING: _ClassVar[Notification.NotificationType]
        DISPLAY_TOAST: _ClassVar[Notification.NotificationType]
    NOTIFICATION_TYPE_INVALID: Notification.NotificationType
    BG_FEED_UPDATE: Notification.NotificationType
    TASK_HAS_RESULT: Notification.NotificationType
    BG_FEED_FEEDBACK_PROCESSED: Notification.NotificationType
    BG_APP_LIST_DIRTY: Notification.NotificationType
    FG_APP_LIST_DIRTY: Notification.NotificationType
    TASK_LIST_DIRTY: Notification.NotificationType
    SESSION_READY: Notification.NotificationType
    SESSION_VERIFICATION_REQUEST: Notification.NotificationType
    SESSION_ADDED: Notification.NotificationType
    SESSION_DENIED: Notification.NotificationType
    SERVER_CLOSING: Notification.NotificationType
    DISPLAY_TOAST: Notification.NotificationType
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ASSOCIATED_ID_FIELD_NUMBER: _ClassVar[int]
    NONE_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    NEW_SESSION_VERIFICATION_FIELD_NUMBER: _ClassVar[int]
    BACKGROUND_APP_NOTIFICATION_FIELD_NUMBER: _ClassVar[int]
    IS_ERROR_FIELD_NUMBER: _ClassVar[int]
    type: Notification.NotificationType
    associated_id: str
    none: _empty_pb2.Empty
    payload: _struct_pb2.Struct
    new_session_verification: _client_session_pb2.NewSessionVerification
    background_app_notification: _background_pb2.BackgroundAppNotification
    is_error: bool
    def __init__(self, type: _Optional[_Union[Notification.NotificationType, str]] = ..., associated_id: _Optional[str] = ..., none: _Optional[_Union[_empty_pb2.Empty, _Mapping]] = ..., payload: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., new_session_verification: _Optional[_Union[_client_session_pb2.NewSessionVerification, _Mapping]] = ..., background_app_notification: _Optional[_Union[_background_pb2.BackgroundAppNotification, _Mapping]] = ..., is_error: bool = ...) -> None: ...
