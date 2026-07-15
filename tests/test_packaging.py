import json
import tomllib
from pathlib import Path

import truffile


ROOT = Path(__file__).resolve().parents[1]


def test_project_version_has_one_source_of_truth():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "version" not in project["project"]
    assert "version" in project["project"]["dynamic"]
    assert project["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "truffile._version.__version__"
    }
    assert truffile.__version__ == "0.4.0"


def test_generated_source_manifest_matches_bundled_packages():
    manifest = json.loads((ROOT / "generated-sources.json").read_text(encoding="utf-8"))

    assert manifest["package"] == "truffile"
    assert len(manifest["sha256"]) == 64
    protocol_files = [
        path
        for path in (ROOT / "truffle").rglob("*")
        if path.is_file() and path.suffix in {".py", ".pyi"}
    ]
    assert len(protocol_files) == manifest["files"]["truffle"]
    assert len(list((ROOT / "truffile" / "app_runtime").rglob("*.py"))) == manifest["files"][
        "truffile/app_runtime"
    ]


def test_source_manifest_includes_release_provenance_files():
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert "GENERATED_SOURCES.md" in manifest
    assert "generated-sources.json" in manifest
    assert "scripts/sync_generated_from_wheel.py" in manifest
