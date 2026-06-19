from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_remote_mcp() -> ModuleType:
    try:
        from truffile.app_runtime import remote_mcp

        return remote_mcp
    except (ImportError, ModuleNotFoundError):
        pass

    loaded_app_runtime = sys.modules.get("app_runtime")
    loaded_truffile_runtime = sys.modules.get("truffile.app_runtime")
    if loaded_app_runtime is loaded_truffile_runtime:
        sys.modules.pop("app_runtime", None)

    try:
        from app_runtime import remote_mcp

        return remote_mcp
    except (ImportError, ModuleNotFoundError):
        pass

    source = _find_pyfw_remote_mcp()
    if source is None:
        raise ModuleNotFoundError("No module named 'truffile.app_runtime.remote_mcp'")

    module_name = "truffile.app_runtime.remote_mcp"
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError("Could not load truffile.app_runtime.remote_mcp")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _find_pyfw_remote_mcp() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "dev" / "pyfw" / "python" / "app_runtime" / "remote_mcp.py"
        if candidate.exists():
            return candidate
    return None
