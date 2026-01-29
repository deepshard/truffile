"""
Genesis - TruffleOS SDK
connect, build, upload, execute
"""
try:
    from ._version import __version__
except ImportError:
    __version__ = "0.1.dev0"

__all__ = ["__version__"]
