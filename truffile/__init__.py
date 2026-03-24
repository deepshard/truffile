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

__all__ = [
    "__version__",
    "TruffleClient",
    "ExecResult",
    "UploadResult",
    "resolve_mdns",
    "NewSessionStatus",
    "parse_runtime_policy",
]
