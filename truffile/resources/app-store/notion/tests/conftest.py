import sys
import importlib
from pathlib import Path


# add app dir to sys.path for local imports
_app_dir = Path(__file__).resolve().parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

_repo_root = _app_dir.parent.parent
_pyfw_python = _repo_root / "dev" / "pyfw" / "python"
if _pyfw_python.exists() and str(_pyfw_python) not in sys.path:
    sys.path.insert(0, str(_pyfw_python))

_remote_mcp_path = _pyfw_python / "app_runtime" / "remote_mcp.py"
if _remote_mcp_path.exists() and "truffile.app_runtime.remote_mcp" not in sys.modules:
    module = importlib.import_module("app_runtime.remote_mcp")
    sys.modules["truffile.app_runtime.remote_mcp"] = module
