from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist
from setuptools.errors import SetupError


REPO_ROOT = Path(__file__).resolve().parent
REQUIRED_PACKAGE_FILES = (
    Path("truffile/app_runtime/__init__.py"),
    Path("truffle/app/app_runtime_pb2.py"),
)


def require_package_inputs() -> None:
    missing = [path for path in REQUIRED_PACKAGE_FILES if not (REPO_ROOT / path).is_file()]
    if missing:
        paths = ", ".join(str(path) for path in missing)
        raise SetupError(
            f"release package inputs are missing: {paths}. "
            "Run `python3.12 scripts/build_package.py --pyfw-path /path/to/pyfw` first."
        )


class VerifiedBuildPy(build_py):
    def run(self) -> None:
        require_package_inputs()
        super().run()


class VerifiedSdist(sdist):
    def run(self) -> None:
        require_package_inputs()
        super().run()


setup(cmdclass={"build_py": VerifiedBuildPy, "sdist": VerifiedSdist})
