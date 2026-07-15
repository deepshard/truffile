from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import empty_pb2 as _empty_pb2
from truffle.os import hardware_stats_pb2 as _hardware_stats_pb2
from truffle.os import client_session_pb2 as _client_session_pb2
from truffle.os import system_mode_pb2 as _system_mode_pb2
from truffle.os import background_feed_pb2 as _background_feed_pb2
from truffle.os import convo_pb2 as _convo_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union
from truffle.os.system_mode_pb2 import RequestSystemModeSetRequest as RequestSystemModeSetRequest
from truffle.os.system_mode_pb2 import RequestSystemModeSetResponse as RequestSystemModeSetResponse
from truffle.os.system_mode_pb2 import GetSystemModeRequest as GetSystemModeRequest
from truffle.os.system_mode_pb2 import GetSystemModeResponse as GetSystemModeResponse
from truffle.os.system_mode_pb2 import SystemModeChangeNotification as SystemModeChangeNotification
from truffle.os.system_mode_pb2 import SystemMode as SystemMode

DESCRIPTOR: _descriptor.FileDescriptor
MODE_INVALID: _system_mode_pb2.SystemMode
MODE_NORMAL: _system_mode_pb2.SystemMode
MODE_DREAM: _system_mode_pb2.SystemMode

class SubscribeToNotificationsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class Notification(_message.Message):
    __slots__ = ("type", "associated_id", "none", "new_session_verification", "feed_entry_notification", "convo_update_notification", "system_mode_change_notification", "is_error")
    class NotificationType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        NOTIFICATION_TYPE_INVALID: _ClassVar[Notification.NotificationType]
        BG_FEED_UPDATE: _ClassVar[Notification.NotificationType]
        TASK_HAS_RESULT: _ClassVar[Notification.NotificationType]
        CONVO_UPDATE: _ClassVar[Notification.NotificationType]
        MODE_CHANGE: _ClassVar[Notification.NotificationType]
        MODE_WILL_CHANGE: _ClassVar[Notification.NotificationType]
        APP_LIST_DIRTY: _ClassVar[Notification.NotificationType]
        TASK_LIST_DIRTY: _ClassVar[Notification.NotificationType]
        BG_AGENT_SCHEDULE_DIRTY: _ClassVar[Notification.NotificationType]
        MEMORY_LIST_DIRTY: _ClassVar[Notification.NotificationType]
        SESSION_READY: _ClassVar[Notification.NotificationType]
        SESSION_VERIFICATION_REQUEST: _ClassVar[Notification.NotificationType]
        SESSION_ADDED: _ClassVar[Notification.NotificationType]
        SESSION_DENIED: _ClassVar[Notification.NotificationType]
        SERVER_CLOSING: _ClassVar[Notification.NotificationType]
        DISPLAY_TOAST: _ClassVar[Notification.NotificationType]
    NOTIFICATION_TYPE_INVALID: Notification.NotificationType
    BG_FEED_UPDATE: Notification.NotificationType
    TASK_HAS_RESULT: Notification.NotificationType
    CONVO_UPDATE: Notification.NotificationType
    MODE_CHANGE: Notification.NotificationType
    MODE_WILL_CHANGE: Notification.NotificationType
    APP_LIST_DIRTY: Notification.NotificationType
    TASK_LIST_DIRTY: Notification.NotificationType
    BG_AGENT_SCHEDULE_DIRTY: Notification.NotificationType
    MEMORY_LIST_DIRTY: Notification.NotificationType
    SESSION_READY: Notification.NotificationType
    SESSION_VERIFICATION_REQUEST: Notification.NotificationType
    SESSION_ADDED: Notification.NotificationType
    SESSION_DENIED: Notification.NotificationType
    SERVER_CLOSING: Notification.NotificationType
    DISPLAY_TOAST: Notification.NotificationType
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ASSOCIATED_ID_FIELD_NUMBER: _ClassVar[int]
    NONE_FIELD_NUMBER: _ClassVar[int]
    NEW_SESSION_VERIFICATION_FIELD_NUMBER: _ClassVar[int]
    FEED_ENTRY_NOTIFICATION_FIELD_NUMBER: _ClassVar[int]
    CONVO_UPDATE_NOTIFICATION_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_MODE_CHANGE_NOTIFICATION_FIELD_NUMBER: _ClassVar[int]
    IS_ERROR_FIELD_NUMBER: _ClassVar[int]
    type: Notification.NotificationType
    associated_id: str
    none: _empty_pb2.Empty
    new_session_verification: _client_session_pb2.NewSessionVerification
    feed_entry_notification: _background_feed_pb2.FeedEntryNotification
    convo_update_notification: _convo_pb2.ConvoUpdateNotification
    system_mode_change_notification: _system_mode_pb2.SystemModeChangeNotification
    is_error: bool
    def __init__(self, type: _Optional[_Union[Notification.NotificationType, str]] = ..., associated_id: _Optional[str] = ..., none: _Optional[_Union[_empty_pb2.Empty, _Mapping]] = ..., new_session_verification: _Optional[_Union[_client_session_pb2.NewSessionVerification, _Mapping]] = ..., feed_entry_notification: _Optional[_Union[_background_feed_pb2.FeedEntryNotification, _Mapping]] = ..., convo_update_notification: _Optional[_Union[_convo_pb2.ConvoUpdateNotification, _Mapping]] = ..., system_mode_change_notification: _Optional[_Union[_system_mode_pb2.SystemModeChangeNotification, _Mapping]] = ..., is_error: bool = ...) -> None: ...
