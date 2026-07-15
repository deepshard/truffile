#!/usr/bin/env python3
"""Refresh the bundled Truffle protocol/runtime packages from a release wheel.

The public source distribution must be independently installable.  This tool
copies the generated ``truffle`` protobuf package and the shared
``truffile.app_runtime`` package from a known-good Truffile wheel, verifies the
wheel checksum when requested, and records provenance in
``generated-sources.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from email.parser import Parser
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "truffle/": ROOT / "truffle",
    "truffile/app_runtime/": ROOT / "truffile" / "app_runtime",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wheel_metadata(archive: zipfile.ZipFile) -> tuple[str, str]:
    metadata_names = [
        name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
    ]
    if len(metadata_names) != 1:
        raise ValueError("wheel must contain exactly one .dist-info/METADATA file")
    metadata = Parser().parsestr(archive.read(metadata_names[0]).decode("utf-8"))
    return metadata.get("Name", ""), metadata.get("Version", "")


def _safe_relative(member: str, prefix: str) -> Path:
    relative = PurePosixPath(member).relative_to(PurePosixPath(prefix))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe wheel member: {member}")
    return Path(*relative.parts)


def sync(wheel: Path, *, expected_sha256: str | None = None) -> dict[str, object]:
    wheel = wheel.expanduser().resolve()
    if not wheel.is_file():
        raise FileNotFoundError(wheel)

    checksum = _sha256(wheel)
    if expected_sha256 and checksum.lower() != expected_sha256.lower():
        raise ValueError(
            f"checksum mismatch: expected {expected_sha256.lower()}, got {checksum.lower()}"
        )

    with zipfile.ZipFile(wheel) as archive:
        package_name, version = _wheel_metadata(archive)
        if package_name.lower() != "truffile":
            raise ValueError(f"expected a truffile wheel, got {package_name!r}")

        selected: dict[str, list[str]] = {}
        for prefix, target in TARGETS.items():
            members = [
                name
                for name in archive.namelist()
                if name.startswith(prefix) and not name.endswith("/")
            ]
            if not members:
                raise ValueError(f"wheel does not contain required package {prefix.rstrip('/')}")
            selected[prefix] = members
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True)

            for member in members:
                destination = target / _safe_relative(member, prefix)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)

    manifest: dict[str, object] = {
        "source_wheel": wheel.name,
        "package": package_name,
        "version": version,
        "sha256": checksum,
        "files": {prefix.rstrip("/"): len(members) for prefix, members in selected.items()},
    }
    (ROOT / "generated-sources.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help="path to a Truffile wheel")
    parser.add_argument(
        "--expected-sha256",
        help="refuse to modify the tree unless the wheel has this SHA-256",
    )
    args = parser.parse_args()
    manifest = sync(args.wheel, expected_sha256=args.expected_sha256)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
