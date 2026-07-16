import tempfile
import unittest
import zipfile
from pathlib import Path
from runpy import run_path
from unittest.mock import patch

from setuptools import Distribution
from setuptools.errors import SetupError

from scripts.build_package import missing_package_inputs, require_package_inputs, stage_package_inputs
from scripts.verify_wheel import REQUIRED_WHEEL_FILES, missing_wheel_files


class TestPackageInputs(unittest.TestCase):
    def test_missing_inputs_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            self.assertEqual(len(missing_package_inputs(repo_root)), 2)
            with self.assertRaisesRegex(RuntimeError, "build_package.py"):
                require_package_inputs(repo_root)

    def test_inputs_are_staged_from_pyfw(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pyfw = root / "pyfw"
            repo = root / "truffile-repo"
            runtime_init = pyfw / "python" / "app_runtime" / "__init__.py"
            proto = pyfw / "python" / "truffle" / "app" / "app_runtime_pb2.py"
            runtime_init.parent.mkdir(parents=True)
            proto.parent.mkdir(parents=True)
            runtime_init.write_text("RUNTIME = True\n", encoding="utf-8")
            proto.write_text("PROTO = True\n", encoding="utf-8")

            stage_package_inputs(pyfw, repo)

            self.assertEqual(missing_package_inputs(repo), [])
            self.assertEqual(
                (repo / "truffile" / "app_runtime" / "__init__.py").read_text(encoding="utf-8"),
                "RUNTIME = True\n",
            )
            self.assertEqual(
                (repo / "truffle" / "app" / "app_runtime_pb2.py").read_text(encoding="utf-8"),
                "PROTO = True\n",
            )

    def test_setuptools_build_rejects_missing_inputs(self):
        setup_path = Path(__file__).resolve().parents[1] / "setup.py"
        with patch("setuptools.setup") as setup, tempfile.TemporaryDirectory() as tmp:
            run_path(str(setup_path))
            verified_build = setup.call_args.kwargs["cmdclass"]["build_py"]
            verified_build.run.__globals__["REPO_ROOT"] = Path(tmp)
            with self.assertRaisesRegex(SetupError, "build_package.py"):
                verified_build(Distribution()).run()


class TestWheelContract(unittest.TestCase):
    def test_missing_wheel_packages_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            wheel = Path(tmp) / "truffile.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("truffile/sdk.py", "")
            missing = missing_wheel_files(wheel)
            self.assertIn("truffile/app_runtime/__init__.py", missing)
            self.assertIn("truffle/app/app_runtime_pb2.py", missing)

    def test_archive_contract_accepts_all_required_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            wheel = Path(tmp) / "truffile.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                for path in REQUIRED_WHEEL_FILES:
                    archive.writestr(path, "")
            self.assertEqual(missing_wheel_files(wheel), [])


if __name__ == "__main__":
    unittest.main()
