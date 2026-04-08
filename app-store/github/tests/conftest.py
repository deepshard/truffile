import os
import sys
from pathlib import Path


# add app dir to sys.path for local imports
_app_dir = Path(__file__).resolve().parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))


def install_stub_env() -> None:
    if "GITHUB_ACCESS_TOKEN" not in os.environ:
        os.environ["GITHUB_ACCESS_TOKEN"] = "gho_stub_test_token"


install_stub_env()
