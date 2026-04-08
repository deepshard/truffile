# truffile SDK — re-exports from app_runtime under the truffile namespace.
#
# usage:
#   from truffile.sdk import ForegroundApp, tool, ok, err
#   from truffile.sdk import BackgroundWorkerApp
#   from truffile.sdk import AppHarness, FakeHttpTransport

from truffile.app_runtime import (
    # app authoring
    ForegroundApp,
    BackgroundApp,
    BackgroundWorkerApp,
    ToolSpec,
    Submission,
    ok,
    err,
    phosphor_icon_url,

    # auth
    OAuth,
    PublicAuth,
    TextConfigAuth,
    load_required_env,

    # protocols
    ApiKeyProvider,
    AuthProvider,
    BrowserSessionProvider,
    HttpResponse,
    HttpTransport,
    OAuthProvider,
    TokenStore,
    CookieStore,

    # stores
    FileTokenStore,
    MemoryTokenStore,
    FileCookieStore,
    MemoryCookieStore,

    # errors
    AppAuthError,
    AppRuntimeFailure,
    AppRuntimeErrorType,

    # testing
    AppHarness,
    FakeApiKeyProvider,
    FakeAuthProvider,
    FakeBackgroundRuntime,
    FakeHttpResponse,
    FakeHttpTransport,
    FakeOAuthProvider,
    HarnessResult,
    RecordedBackgroundError,
    RecordedSubmission,
    make_background_ctx,

    # mcp testing
    McpTestServer,
    call_tool,
    InProcessGrpcServer,

    # utilities
    parse_jsonrpc_payload,
    HttpxResponseAdapter,
    report_app_error,
    truncate_result,
    truncate_items,
)

# nice alias — truffile.sdk.tool is ToolSpec
tool = ToolSpec
