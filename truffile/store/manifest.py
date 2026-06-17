from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Any

import httpx
import yaml


DEFAULT_STORE_MANIFEST_URL = "https://defaultapps.itsalltruffles.com/manifest_dev.staging.json"
USER_AGENT = "truffile-cli/0.2"


@dataclass(frozen=True)
class StoreRelease:
    bundle_sha256: str
    bundle_url: str
    display_version: str
    release_notes: str
    released_at: str


@dataclass(frozen=True)
class StoreApp:
    name: str
    bundle_id: str
    description: str
    bundle_url: str
    provides_foreground: bool
    provides_background: bool
    tools_count: int
    latest_release: StoreRelease | None

    @property
    def effective_bundle_url(self) -> str:
        if self.latest_release and self.latest_release.bundle_url:
            return self.latest_release.bundle_url
        return self.bundle_url

    @property
    def latest_sha(self) -> str:
        return self.latest_release.bundle_sha256 if self.latest_release else ""


@dataclass(frozen=True)
class BundleClassification:
    base_image: str
    is_browser: bool
    reason: str


def _get(obj: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in obj:
            return obj[key]
    return default


def parse_store_manifest(payload: dict[str, Any]) -> list[StoreApp]:
    apps: list[StoreApp] = []
    for raw_app in payload.get("apps", []) or []:
        if not isinstance(raw_app, dict):
            continue
        metadata = raw_app.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        release_obj = _get(raw_app, "latestRelease", "latest_release", default=None)
        release = None
        if isinstance(release_obj, dict):
            release = StoreRelease(
                bundle_sha256=str(_get(release_obj, "bundleSha256", "bundle_sha256")).strip(),
                bundle_url=str(_get(release_obj, "bundleUrl", "bundle_url")).strip(),
                display_version=str(_get(release_obj, "displayVersion", "display_version")).strip(),
                release_notes=str(_get(release_obj, "releaseNotes", "release_notes")).strip(),
                released_at=str(_get(release_obj, "releasedAt", "released_at")).strip(),
            )
        app = StoreApp(
            name=str(_get(metadata, "name")).strip(),
            bundle_id=str(_get(metadata, "bundleId", "bundle_id")).strip(),
            description=str(_get(metadata, "description")).strip(),
            bundle_url=str(_get(raw_app, "bundleUrl", "bundle_url")).strip(),
            provides_foreground=bool(_get(raw_app, "providesForeground", "provides_foreground", default=False)),
            provides_background=bool(_get(raw_app, "providesBackground", "provides_background", default=False)),
            tools_count=len(raw_app.get("tools") or []),
            latest_release=release,
        )
        if app.name and (app.bundle_id or app.effective_bundle_url):
            apps.append(app)
    return apps


async def fetch_store_apps(
    *,
    manifest_url: str = DEFAULT_STORE_MANIFEST_URL,
    client: httpx.AsyncClient | None = None,
) -> list[StoreApp]:
    close_client = client is None
    http = client or httpx.AsyncClient(timeout=30.0, headers={"User-Agent": USER_AGENT})
    try:
        response = await http.get(manifest_url)
        response.raise_for_status()
        return parse_store_manifest(response.json())
    finally:
        if close_client:
            await http.aclose()


async def fetch_bundle_bytes(bundle_url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60.0, headers={"User-Agent": USER_AGENT}) as client:
        response = await client.get(bundle_url)
        response.raise_for_status()
        return response.content


def classify_bundle_bytes(bundle_bytes: bytes) -> BundleClassification:
    try:
        with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as archive:
            names = archive.namelist()
            truffile_name = next(
                (name for name in names if name.rstrip("/") == "truffile.yaml"),
                None,
            )
            if truffile_name is None:
                return BundleClassification(
                    base_image="unknown",
                    is_browser=False,
                    reason="truffile.yaml not found in bundle",
                )
            data = yaml.safe_load(archive.read(truffile_name).decode("utf-8")) or {}
    except Exception as exc:
        return BundleClassification(
            base_image="unknown",
            is_browser=False,
            reason=f"could not inspect bundle: {exc}",
        )

    if not isinstance(data, dict):
        return BundleClassification(
            base_image="unknown",
            is_browser=False,
            reason="truffile.yaml root is not an object",
        )

    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    explicit_base = str(metadata.get("base_image") or "").strip().lower()
    if explicit_base == "browser":
        return BundleClassification(
            base_image="browser",
            is_browser=True,
            reason="metadata.base_image is browser",
        )

    steps = data.get("steps") if isinstance(data.get("steps"), list) else []
    has_vnc = any(
        isinstance(step, dict) and str(step.get("type") or "").strip().lower() == "vnc"
        for step in steps
    )
    if has_vnc:
        return BundleClassification(
            base_image="browser",
            is_browser=True,
            reason="bundle has a vnc install step",
        )

    base_image = explicit_base or "minimal"
    return BundleClassification(
        base_image=base_image,
        is_browser=False,
        reason=f"base image is {base_image}",
    )


def store_lookup_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def find_store_app(apps: list[StoreApp], selector: str) -> StoreApp:
    needle = selector.strip()
    if not needle:
        raise ValueError("app selector is required")
    lower = needle.lower()
    slug = store_lookup_key(needle)

    matches = [
        app for app in apps
        if app.bundle_id.lower() == lower
        or app.name.lower() == lower
        or store_lookup_key(app.name) == slug
        or store_lookup_key(app.bundle_id) == slug
    ]
    if not matches:
        raise ValueError(f"No store app matched '{selector}'")
    if len(matches) > 1:
        names = ", ".join(app.name for app in matches[:5])
        raise ValueError(f"App selector '{selector}' is ambiguous: {names}")
    return matches[0]
