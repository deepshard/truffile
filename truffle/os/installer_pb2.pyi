from truffle.app import app_pb2 as _app_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union
from truffle.app.app_pb2 import AppMetadata as AppMetadata
from truffle.app.app_pb2 import AppConfig as AppConfig
from truffle.app.app_pb2 import App as App
from truffle.app.app_pb2 import AppError as AppError

DESCRIPTOR: _descriptor.FileDescriptor

class AppInstallSourceType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    APP_INSTALL_SOURCE_TYPE_UNSPECIFIED: _ClassVar[AppInstallSourceType]
    APP_INSTALL_SOURCE_TYPE_URL: _ClassVar[AppInstallSourceType]
    APP_INSTALL_SOURCE_TYPE_FILE: _ClassVar[AppInstallSourceType]
    APP_INSTALL_SOURCE_TYPE_GIT: _ClassVar[AppInstallSourceType]
APP_INSTALL_SOURCE_TYPE_UNSPECIFIED: AppInstallSourceType
APP_INSTALL_SOURCE_TYPE_URL: AppInstallSourceType
APP_INSTALL_SOURCE_TYPE_FILE: AppInstallSourceType
APP_INSTALL_SOURCE_TYPE_GIT: AppInstallSourceType

class AppInstallSource(_message.Message):
    __slots__ = ("source_type", "url", "git_hash")
    SOURCE_TYPE_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    GIT_HASH_FIELD_NUMBER: _ClassVar[int]
    source_type: AppInstallSourceType
    url: str
    git_hash: str
    def __init__(self, source_type: _Optional[_Union[AppInstallSourceType, str]] = ..., url: _Optional[str] = ..., git_hash: _Optional[str] = ...) -> None: ...

class AppInstallModal(_message.Message):
    __slots__ = ("step_index", "step_name", "welcome_modal", "text_fields_modal", "vnc_modal", "finish_modal", "upload_file_modal", "oauth_modal")
    class WelcomeModal(_message.Message):
        __slots__ = ("welcome_message",)
        WELCOME_MESSAGE_FIELD_NUMBER: _ClassVar[int]
        welcome_message: str
        def __init__(self, welcome_message: _Optional[str] = ...) -> None: ...
    class TextFieldsModal(_message.Message):
        __slots__ = ("instructions", "fields")
        class TextField(_message.Message):
            __slots__ = ("label", "placeholder", "is_password", "default_value")
            LABEL_FIELD_NUMBER: _ClassVar[int]
            PLACEHOLDER_FIELD_NUMBER: _ClassVar[int]
            IS_PASSWORD_FIELD_NUMBER: _ClassVar[int]
            DEFAULT_VALUE_FIELD_NUMBER: _ClassVar[int]
            label: str
            placeholder: str
            is_password: bool
            default_value: str
            def __init__(self, label: _Optional[str] = ..., placeholder: _Optional[str] = ..., is_password: bool = ..., default_value: _Optional[str] = ...) -> None: ...
        class FieldsEntry(_message.Message):
            __slots__ = ("key", "value")
            KEY_FIELD_NUMBER: _ClassVar[int]
            VALUE_FIELD_NUMBER: _ClassVar[int]
            key: str
            value: AppInstallModal.TextFieldsModal.TextField
            def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[AppInstallModal.TextFieldsModal.TextField, _Mapping]] = ...) -> None: ...
        INSTRUCTIONS_FIELD_NUMBER: _ClassVar[int]
        FIELDS_FIELD_NUMBER: _ClassVar[int]
        instructions: str
        fields: _containers.MessageMap[str, AppInstallModal.TextFieldsModal.TextField]
        def __init__(self, instructions: _Optional[str] = ..., fields: _Optional[_Mapping[str, AppInstallModal.TextFieldsModal.TextField]] = ...) -> None: ...
    class VNCModal(_message.Message):
        __slots__ = ("instructions", "vnc_uri_path", "closes_on_complete")
        INSTRUCTIONS_FIELD_NUMBER: _ClassVar[int]
        VNC_URI_PATH_FIELD_NUMBER: _ClassVar[int]
        CLOSES_ON_COMPLETE_FIELD_NUMBER: _ClassVar[int]
        instructions: str
        vnc_uri_path: str
        closes_on_complete: bool
        def __init__(self, instructions: _Optional[str] = ..., vnc_uri_path: _Optional[str] = ..., closes_on_complete: bool = ...) -> None: ...
    class OAuthModal(_message.Message):
        __slots__ = ("instructions", "provider", "auth_url", "state")
        INSTRUCTIONS_FIELD_NUMBER: _ClassVar[int]
        PROVIDER_FIELD_NUMBER: _ClassVar[int]
        AUTH_URL_FIELD_NUMBER: _ClassVar[int]
        STATE_FIELD_NUMBER: _ClassVar[int]
        instructions: str
        provider: str
        auth_url: str
        state: str
        def __init__(self, instructions: _Optional[str] = ..., provider: _Optional[str] = ..., auth_url: _Optional[str] = ..., state: _Optional[str] = ...) -> None: ...
    class UploadFileModal(_message.Message):
        __slots__ = ("upload_uri_path",)
        UPLOAD_URI_PATH_FIELD_NUMBER: _ClassVar[int]
        upload_uri_path: str
        def __init__(self, upload_uri_path: _Optional[str] = ...) -> None: ...
    class FinishModal(_message.Message):
        __slots__ = ("app_uuid", "finish_message")
        APP_UUID_FIELD_NUMBER: _ClassVar[int]
        FINISH_MESSAGE_FIELD_NUMBER: _ClassVar[int]
        app_uuid: str
        finish_message: str
        def __init__(self, app_uuid: _Optional[str] = ..., finish_message: _Optional[str] = ...) -> None: ...
    STEP_INDEX_FIELD_NUMBER: _ClassVar[int]
    STEP_NAME_FIELD_NUMBER: _ClassVar[int]
    WELCOME_MODAL_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELDS_MODAL_FIELD_NUMBER: _ClassVar[int]
    VNC_MODAL_FIELD_NUMBER: _ClassVar[int]
    FINISH_MODAL_FIELD_NUMBER: _ClassVar[int]
    UPLOAD_FILE_MODAL_FIELD_NUMBER: _ClassVar[int]
    OAUTH_MODAL_FIELD_NUMBER: _ClassVar[int]
    step_index: int
    step_name: str
    welcome_modal: AppInstallModal.WelcomeModal
    text_fields_modal: AppInstallModal.TextFieldsModal
    vnc_modal: AppInstallModal.VNCModal
    finish_modal: AppInstallModal.FinishModal
    upload_file_modal: AppInstallModal.UploadFileModal
    oauth_modal: AppInstallModal.OAuthModal
    def __init__(self, step_index: _Optional[int] = ..., step_name: _Optional[str] = ..., welcome_modal: _Optional[_Union[AppInstallModal.WelcomeModal, _Mapping]] = ..., text_fields_modal: _Optional[_Union[AppInstallModal.TextFieldsModal, _Mapping]] = ..., vnc_modal: _Optional[_Union[AppInstallModal.VNCModal, _Mapping]] = ..., finish_modal: _Optional[_Union[AppInstallModal.FinishModal, _Mapping]] = ..., upload_file_modal: _Optional[_Union[AppInstallModal.UploadFileModal, _Mapping]] = ..., oauth_modal: _Optional[_Union[AppInstallModal.OAuthModal, _Mapping]] = ...) -> None: ...

class AppInstallError(_message.Message):
    __slots__ = ("error_message",)
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    error_message: str
    def __init__(self, error_message: _Optional[str] = ...) -> None: ...

class AppInstallLoading(_message.Message):
    __slots__ = ("loading_message",)
    LOADING_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    loading_message: str
    def __init__(self, loading_message: _Optional[str] = ...) -> None: ...

class AppInstallHint(_message.Message):
    __slots__ = ("ui_state",)
    class UiState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        UI_STATE_UNSPECIFIED: _ClassVar[AppInstallHint.UiState]
        UI_STATE_USER_INTERACTION_READY: _ClassVar[AppInstallHint.UiState]
        UI_STATE_MOVE_TO_BACKGROUND: _ClassVar[AppInstallHint.UiState]
    UI_STATE_UNSPECIFIED: AppInstallHint.UiState
    UI_STATE_USER_INTERACTION_READY: AppInstallHint.UiState
    UI_STATE_MOVE_TO_BACKGROUND: AppInstallHint.UiState
    UI_STATE_FIELD_NUMBER: _ClassVar[int]
    ui_state: AppInstallHint.UiState
    def __init__(self, ui_state: _Optional[_Union[AppInstallHint.UiState, str]] = ...) -> None: ...

class AppInstallMetadata(_message.Message):
    __slots__ = ("uuid", "metadata", "has_foreground", "has_background")
    UUID_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    HAS_FOREGROUND_FIELD_NUMBER: _ClassVar[int]
    HAS_BACKGROUND_FIELD_NUMBER: _ClassVar[int]
    uuid: str
    metadata: _app_pb2.AppMetadata
    has_foreground: bool
    has_background: bool
    def __init__(self, uuid: _Optional[str] = ..., metadata: _Optional[_Union[_app_pb2.AppMetadata, _Mapping]] = ..., has_foreground: bool = ..., has_background: bool = ...) -> None: ...

class AppInstallUserAction(_message.Message):
    __slots__ = ("next", "text_fields", "abort", "oauth")
    class NextAction(_message.Message):
        __slots__ = ()
        def __init__(self) -> None: ...
    class SubmitTextFieldsAction(_message.Message):
        __slots__ = ("field_responses",)
        class FieldResponsesEntry(_message.Message):
            __slots__ = ("key", "value")
            KEY_FIELD_NUMBER: _ClassVar[int]
            VALUE_FIELD_NUMBER: _ClassVar[int]
            key: str
            value: str
            def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
        FIELD_RESPONSES_FIELD_NUMBER: _ClassVar[int]
        field_responses: _containers.ScalarMap[str, str]
        def __init__(self, field_responses: _Optional[_Mapping[str, str]] = ...) -> None: ...
    class SubmitOAuthAction(_message.Message):
        __slots__ = ("code", "state")
        CODE_FIELD_NUMBER: _ClassVar[int]
        STATE_FIELD_NUMBER: _ClassVar[int]
        code: str
        state: str
        def __init__(self, code: _Optional[str] = ..., state: _Optional[str] = ...) -> None: ...
    class AbortAction(_message.Message):
        __slots__ = ()
        def __init__(self) -> None: ...
    NEXT_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELDS_FIELD_NUMBER: _ClassVar[int]
    ABORT_FIELD_NUMBER: _ClassVar[int]
    OAUTH_FIELD_NUMBER: _ClassVar[int]
    next: AppInstallUserAction.NextAction
    text_fields: AppInstallUserAction.SubmitTextFieldsAction
    abort: AppInstallUserAction.AbortAction
    oauth: AppInstallUserAction.SubmitOAuthAction
    def __init__(self, next: _Optional[_Union[AppInstallUserAction.NextAction, _Mapping]] = ..., text_fields: _Optional[_Union[AppInstallUserAction.SubmitTextFieldsAction, _Mapping]] = ..., abort: _Optional[_Union[AppInstallUserAction.AbortAction, _Mapping]] = ..., oauth: _Optional[_Union[AppInstallUserAction.SubmitOAuthAction, _Mapping]] = ...) -> None: ...

class AppInstallRequest(_message.Message):
    __slots__ = ("start_new", "user_action")
    class StartNewInstall(_message.Message):
        __slots__ = ("source",)
        SOURCE_FIELD_NUMBER: _ClassVar[int]
        source: AppInstallSource
        def __init__(self, source: _Optional[_Union[AppInstallSource, _Mapping]] = ...) -> None: ...
    START_NEW_FIELD_NUMBER: _ClassVar[int]
    USER_ACTION_FIELD_NUMBER: _ClassVar[int]
    start_new: AppInstallRequest.StartNewInstall
    user_action: AppInstallUserAction
    def __init__(self, start_new: _Optional[_Union[AppInstallRequest.StartNewInstall, _Mapping]] = ..., user_action: _Optional[_Union[AppInstallUserAction, _Mapping]] = ...) -> None: ...

class AppInstallResponse(_message.Message):
    __slots__ = ("install_modal", "install_error", "install_loading", "install_metadata", "install_hint")
    INSTALL_MODAL_FIELD_NUMBER: _ClassVar[int]
    INSTALL_ERROR_FIELD_NUMBER: _ClassVar[int]
    INSTALL_LOADING_FIELD_NUMBER: _ClassVar[int]
    INSTALL_METADATA_FIELD_NUMBER: _ClassVar[int]
    INSTALL_HINT_FIELD_NUMBER: _ClassVar[int]
    install_modal: AppInstallModal
    install_error: AppInstallError
    install_loading: AppInstallLoading
    install_metadata: AppInstallMetadata
    install_hint: AppInstallHint
    def __init__(self, install_modal: _Optional[_Union[AppInstallModal, _Mapping]] = ..., install_error: _Optional[_Union[AppInstallError, _Mapping]] = ..., install_loading: _Optional[_Union[AppInstallLoading, _Mapping]] = ..., install_metadata: _Optional[_Union[AppInstallMetadata, _Mapping]] = ..., install_hint: _Optional[_Union[AppInstallHint, _Mapping]] = ...) -> None: ...
