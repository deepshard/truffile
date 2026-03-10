import os

# Keep gRPC from enabling fork support in this CLI process.
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "false"

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
