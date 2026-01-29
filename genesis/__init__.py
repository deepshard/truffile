try:
    from ._version import __version__
except ImportError:
    __version__ = "0.1.dev0"

from .client import TruffleClient, ExecResult

__all__ = ["__version__", "TruffleClient", "ExecResult"]
