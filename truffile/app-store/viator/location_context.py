from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import time
from urllib.request import urlopen


logger = logging.getLogger("viator.location")


@dataclass(slots=True)
class CoarseLocation:
    city: str = ""
    region: str = ""
    country: str = ""
    zip: str = ""
    lat: float | None = None
    lon: float | None = None
    timezone: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> CoarseLocation | None:
        city = str(payload.get("city") or "").strip()
        region = str(payload.get("regionName") or payload.get("region") or "").strip()
        country = str(payload.get("country") or "").strip()
        if not any((city, region, country)):
            return None
        lat = payload.get("lat")
        lon = payload.get("lon")
        return cls(
            city=city,
            region=region,
            country=country,
            zip=str(payload.get("zip") or "").strip(),
            lat=float(lat) if isinstance(lat, (float, int)) else None,
            lon=float(lon) if isinstance(lon, (float, int)) else None,
            timezone=str(payload.get("timezone") or "").strip(),
        )

    def label(self) -> str:
        return ", ".join(part for part in (self.city, self.region, self.country) if part)

    def destination(self) -> str:
        return ", ".join(part for part in (self.city, self.region) if part) or self.label()


def env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _location_from_env() -> CoarseLocation | None:
    raw_json = os.getenv("TRUFFLE_USER_LOCATION_JSON", "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            location = CoarseLocation.from_mapping(parsed)
            if location:
                return location

    return CoarseLocation.from_mapping(
        {
            "city": os.getenv("TRUFFLE_USER_CITY", ""),
            "regionName": os.getenv("TRUFFLE_USER_REGION", ""),
            "country": os.getenv("TRUFFLE_USER_COUNTRY", ""),
            "zip": os.getenv("TRUFFLE_USER_ZIP", ""),
            "timezone": os.getenv("TRUFFLE_USER_TIMEZONE", ""),
        }
    )


def _read_location_cache(cache_file: Path, *, max_age_seconds: int) -> CoarseLocation | None:
    try:
        if not cache_file.exists() or time.time() - cache_file.stat().st_mtime > max_age_seconds:
            return None
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return CoarseLocation.from_mapping(payload)


def _fetch_ip_location() -> dict[str, object] | None:
    try:
        with urlopen("https://api.ipify.org", timeout=5) as response:
            ip = response.read().decode("utf-8").strip()
        if not ip:
            return None
        with urlopen(f"http://ip-api.com/json/{ip}", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.info("Could not fetch coarse IP location: %s", exc)
        return None
    return payload if isinstance(payload, dict) and payload.get("status") == "success" else None


def get_cached_user_location(*, fetch_if_missing: bool = True) -> CoarseLocation | None:
    env_location = _location_from_env()
    if env_location:
        return env_location

    cache_file = Path(os.getenv("TRUFFLE_LOCATION_CACHE_FILE", "/tmp/truffle_user_location.json"))
    cached = _read_location_cache(
        cache_file,
        max_age_seconds=env_int("TRUFFLE_LOCATION_CACHE_MAX_AGE_HOURS", 24, minimum=1) * 3600,
    )
    if cached or not fetch_if_missing or os.getenv("TRUFFLE_DISABLE_IP_LOCATION", "").strip() == "1":
        return cached

    payload = _fetch_ip_location()
    if not payload:
        return None
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        logger.info("Could not cache coarse IP location: %s", exc)
    return CoarseLocation.from_mapping(payload)
