import os
import sys
from pathlib import Path

# Keep gRPC from enabling fork support in this CLI process.
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "false"


def _ensure_bundled_truffle_on_path() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    bundled_truffle = repo_root / "truffle"
    if not bundled_truffle.is_dir():
        return

    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


_ensure_bundled_truffle_on_path()

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.1.dev0"

from .client import TruffleClient, ExecResult, UploadResult, resolve_mdns, NewSessionStatus
from .schedule import parse_runtime_policy

try:
    from .sdk import (
        ForegroundApp,
        BackgroundWorkerApp,
        tool,
        ok,
        err,
        OAuth,
        AppHarness,
        ToolSpec,
    )

    # register app_runtime as an alias for truffile.app_runtime
    # so old apps using "from app_runtime import ..." still work
    # when only truffile is installed (no standalone app_runtime)
    import truffile.app_runtime as _app_runtime
    if "app_runtime" not in sys.modules:
        sys.modules["app_runtime"] = _app_runtime
        # register submodules so deep imports work too
        for _submod in ("background", "mcp", "abrasive", "browser", "browser.web_fingerprint"):
            _full = f"truffile.app_runtime.{_submod}"
            _alias = f"app_runtime.{_submod}"
            if _full in sys.modules and _alias not in sys.modules:
                sys.modules[_alias] = sys.modules[_full]
except ImportError:
    pass

__all__ = [
    "__version__",
    "TruffleClient",
    "ExecResult",
    "UploadResult",
    "resolve_mdns",
    "NewSessionStatus",
    "parse_runtime_policy",
    "ForegroundApp",
    "BackgroundWorkerApp",
    "tool",
    "ok",
    "err",
    "OAuth",
    "AppHarness",
    "ToolSpec",
]
