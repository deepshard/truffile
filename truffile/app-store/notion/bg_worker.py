from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib import error as urlerror
from urllib import request as urlrequest

from truffile.app_runtime.errors import AppAuthError, AppRuntimeFailure

from auth import NotionAuth
from bg_state import BackgroundState, LastDigest, digest_hash, utc_now_iso
from config import (
    DEFAULT_DATA_DIR,
    NOTION_API_BASE,
    NOTION_API_VERSION,
    NOTION_BACKGROUND_SOURCE,
    NOTION_BACKGROUND_MAX_ITEMS,
    NOTION_MCP_BASE,
    build_default_headers,
)
from notion_client import NotionMcpClient


LOGGER = logging.getLogger("notion.bg_worker")
NOTION_URL_RE = re.compile(r"https://(?:www\.)?notion\.(?:so|site)/[^\s)>\"]+")
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}")


@dataclass(frozen=True, slots=True)
class NotionChangeRecord:
    key: str
    title: str
    object_type: str
    url: str
    last_edited_time: str
    last_edited_by: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class DigestRunResult:
    summary: str | None
    stats: dict[str, Any]
    digest_hash: str
    generated_at: str
    uris: list[str]


def _parse_iso(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _clean_text(text: str, limit: int = 180) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "..."


def _json_fingerprint(payload: dict[str, Any]) -> str:
    return digest_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _mcp_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if not isinstance(result, dict):
        return str(result)
    parts: list[str] = []
    for key in ("text", "message", "answer", "summary"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text", "") or "").strip()
                if text:
                    parts.append(text)
    provider = result.get("provider_result")
    if isinstance(provider, dict):
        provider_text = _mcp_text(provider)
        if provider_text.strip():
            parts.append(provider_text)
    return "\n".join(dict.fromkeys(part for part in parts if part)).strip()


def _mcp_structured(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    structured = result.get("structuredContent")
    if structured is not None:
        return structured
    provider = result.get("provider_result")
    if provider is not None:
        return _mcp_structured(provider)
    return result


def _mcp_resources(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    out: list[dict[str, Any]] = []
    resources = result.get("resources")
    if isinstance(resources, list):
        out.extend(item for item in resources if isinstance(item, dict))
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict) or item.get("type") not in {"resource", "resource_link"}:
                continue
            resource = item.get("resource") if isinstance(item.get("resource"), dict) else item
            if isinstance(resource, dict):
                out.append(resource)
    provider = result.get("provider_result")
    if provider is not None:
        out.extend(_mcp_resources(provider))
    deduped: dict[str, dict[str, Any]] = {}
    for resource in out:
        key = str(resource.get("uri") or resource.get("url") or resource.get("name") or resource.get("title") or "")
        if key:
            deduped[key] = resource
    return list(deduped.values())


def _collect_dicts(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        out.append(value)
        for child in value.values():
            out.extend(_collect_dicts(child))
    elif isinstance(value, list):
        for item in value:
            out.extend(_collect_dicts(item))
    return out


def _first_str(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        return str(tool.get("name") or tool.get("public_name") or "")
    return str(getattr(tool, "public_name", getattr(tool, "name", "")) or "")


def _mcp_title(value: Any) -> str:
    if isinstance(value, str):
        return _clean_text(value, 100)
    if isinstance(value, list):
        return _clean_text(" ".join(str(item.get("plain_text", "") if isinstance(item, dict) else item) for item in value), 100)
    if isinstance(value, dict):
        for key in ("plain_text", "text", "title", "name"):
            title = _mcp_title(value.get(key))
            if title:
                return title
    return ""


def _json_from_text(text: str) -> Any | None:
    raw = str(text or "").strip()
    if not raw or raw[0] not in "[{":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _notion_text(rich_text: Any) -> str:
    if not isinstance(rich_text, list):
        return ""
    parts: list[str] = []
    for item in rich_text:
        if not isinstance(item, dict):
            continue
        plain = str(item.get("plain_text", "") or "").strip()
        if plain:
            parts.append(plain)
    return "".join(parts).strip()


def _notion_title(obj: dict[str, Any]) -> str:
    if str(obj.get("object", "") or "") == "database":
        return _notion_text(obj.get("title")) or "Untitled database"
    properties = obj.get("properties")
    if isinstance(properties, dict):
        for prop in properties.values():
            if isinstance(prop, dict) and prop.get("type") == "title":
                title = _notion_text(prop.get("title"))
                if title:
                    return title
    return str(obj.get("title", "") or "").strip() or "Untitled page"


def _notion_user_label(raw: Any) -> str:
    if not isinstance(raw, dict):
        return "unknown"
    name = str(raw.get("name", "") or "").strip()
    if name:
        return name
    person = raw.get("person")
    if isinstance(person, dict):
        email = str(person.get("email", "") or "").strip()
        if email:
            return email
    user_id = str(raw.get("id", "") or "").strip()
    return user_id or "unknown"


def _record_from_api_result(obj: dict[str, Any]) -> NotionChangeRecord | None:
    item_id = str(obj.get("id", "") or "").strip()
    if not item_id:
        return None
    object_type = str(obj.get("object", "") or "page").strip() or "page"
    title = _notion_title(obj)
    url = str(obj.get("url", "") or "").strip()
    edited = str(obj.get("last_edited_time", "") or "").strip()
    edited_by = _notion_user_label(obj.get("last_edited_by"))
    fingerprint = _json_fingerprint(
        {
            "id": item_id,
            "title": title,
            "object": object_type,
            "url": url,
            "last_edited_time": edited,
            "last_edited_by": edited_by,
        }
    )
    return NotionChangeRecord(
        key=item_id,
        title=title,
        object_type=object_type,
        url=url,
        last_edited_time=edited,
        last_edited_by=edited_by,
        fingerprint=fingerprint,
    )


def _record_from_mcp_item(item: dict[str, Any]) -> NotionChangeRecord | None:
    title = (
        _mcp_title(item.get("title"))
        or _mcp_title(item.get("name"))
        or _mcp_title(item.get("page_title"))
        or _mcp_title(item.get("database_title"))
        or _mcp_title(item.get("summary"))
    )
    url = _first_str(item, ("url", "href", "link", "public_url", "notion_url"))
    item_id = _first_str(item, ("id", "page_id", "database_id", "object_id"))
    edited = _first_str(item, ("last_edited_time", "lastEditedTime", "updated_at", "updatedAt", "edited", "timestamp"))
    edited_by = _first_str(item, ("last_edited_by", "lastEditedBy", "edited_by", "editor", "author", "created_by"))
    object_type = _first_str(item, ("object", "type", "object_type")) or "page"
    if not item_id and url:
        match = UUID_RE.search(url)
        if match:
            item_id = match.group(0)
    if not title and not url and not item_id:
        return None
    key = item_id or url or digest_hash(json.dumps(item, sort_keys=True, default=str))
    fingerprint = _json_fingerprint(
        {
            "key": key,
            "title": title,
            "object": object_type,
            "url": url,
            "last_edited_time": edited,
            "last_edited_by": edited_by,
        }
    )
    return NotionChangeRecord(
        key=key,
        title=title or "Untitled Notion item",
        object_type=object_type,
        url=url,
        last_edited_time=edited,
        last_edited_by=edited_by or "unknown",
        fingerprint=fingerprint,
    )


def _record_from_mcp_resource(resource: dict[str, Any]) -> NotionChangeRecord | None:
    uri = _first_str(resource, ("uri", "url", "href", "link"))
    title = (
        _mcp_title(resource.get("title"))
        or _mcp_title(resource.get("name"))
        or _mcp_title(resource.get("description"))
    )
    if not uri and not title:
        return None
    item_id = _first_str(resource, ("id", "page_id", "database_id"))
    if not item_id and uri:
        match = UUID_RE.search(uri)
        if match:
            item_id = match.group(0)
    mime = _first_str(resource, ("mimeType", "mime_type"))
    object_type = "database" if "database" in mime.lower() else "page"
    key = item_id or uri or digest_hash(json.dumps(resource, sort_keys=True, default=str))
    url = uri if uri.startswith("http") else ""
    fingerprint = _json_fingerprint(
        {
            "key": key,
            "title": title,
            "object": object_type,
            "uri": uri,
            "mime": mime,
        }
    )
    return NotionChangeRecord(
        key=key,
        title=title or "Untitled Notion item",
        object_type=object_type,
        url=url,
        last_edited_time="",
        last_edited_by="unknown",
        fingerprint=fingerprint,
    )


def _notion_fetch_arg(record: NotionChangeRecord) -> dict[str, str]:
    return {"id": record.url or record.key}


class NotionBackgroundWorker:
    def __init__(
        self,
        *,
        client: Any | None = None,
        state_file: Path | None = None,
        auth: NotionAuth | None = None,
        api_post: Callable[[str, dict[str, Any], str], dict[str, Any]] | None = None,
        max_items: int = NOTION_BACKGROUND_MAX_ITEMS,
        background_source: str = NOTION_BACKGROUND_SOURCE,
    ) -> None:
        self.client = client
        self._owns_client = client is None
        self.auth = auth or NotionAuth()
        self.state_file = Path(state_file) if state_file is not None else DEFAULT_DATA_DIR / "background-state.json"
        self.max_items = max(1, int(max_items))
        self._api_post = api_post or self._post_notion_api
        self.background_source = str(background_source or "mcp").strip().lower()
        self.state = self._load_state()
        self._last_digest: LastDigest | None = None

    def _build_client(self) -> NotionMcpClient:
        return NotionMcpClient(
            remote_url=NOTION_MCP_BASE,
            auth=self.auth,
            default_headers=build_default_headers(),
        )

    def _get_client(self, *, force_rebuild: bool = False) -> Any:
        if self.client is not None and not (force_rebuild and self._owns_client):
            return self.client
        if self.client is not None and self._owns_client:
            close = getattr(self.client, "close", None)
            if callable(close):
                close()
        self.client = self._build_client()
        return self.client

    def verify(self) -> tuple[bool, str]:
        return self._get_client(force_rebuild=self._owns_client).verify()

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

    def run_cycle(self) -> DigestRunResult:
        run_started = utc_now_iso()
        previous_run = self.state.last_run_at
        source = "notion_mcp_search"
        api_error = ""
        workspace = self._workspace_label()

        if self.background_source == "api":
            source = "notion_api"
            try:
                records = self._scan_with_notion_api()
            except AppAuthError:
                raise
            except Exception as exc:
                LOGGER.info("Notion API changelog scan failed, falling back to hosted MCP search: %s", exc)
                api_error = str(exc)
                source = "notion_mcp_search"
                records = self._scan_with_mcp_search(previous_run)
        else:
            records = self._scan_with_mcp_search(previous_run)

        changed = self._changed_records(records, previous_run)
        for record in records:
            self.state.page_fingerprints[record.key] = record.fingerprint

        stats = {
            "source": source,
            "scanned": len(records),
            "changed": len(changed),
            "previous_run_at": previous_run,
            "last_run_at": run_started,
            "api_error": api_error,
            "state_file": str(self.state_file),
            "workspace": workspace,
        }
        self.state.last_run_at = run_started
        self.state.last_stats = stats

        summary: str | None = None
        uris = [record.url for record in changed if record.url]
        if previous_run and changed:
            summary = self._build_digest(previous_run, run_started, changed, stats)
            self.state.last_digest_at = run_started
            self.state.last_digest_hash = digest_hash(summary)
            self._last_digest = LastDigest(run_started, self.state.last_digest_hash, summary, stats)
        elif not previous_run:
            stats["skip_reason"] = "baseline_created"
            baseline_records = records[: self.max_items]
            uris = [record.url for record in baseline_records if record.url]
            summary = self._build_baseline_digest(run_started, baseline_records, stats)
            self.state.last_digest_at = run_started
            self.state.last_digest_hash = digest_hash(summary)
            self._last_digest = LastDigest(run_started, self.state.last_digest_hash, summary, stats)

        self._save_state()
        return DigestRunResult(
            summary=summary,
            stats=stats,
            digest_hash=digest_hash(summary or ""),
            generated_at=run_started,
            uris=uris,
        )

    def _changed_records(self, records: list[NotionChangeRecord], previous_run: str) -> list[NotionChangeRecord]:
        if not previous_run:
            return []
        previous_dt = _parse_iso(previous_run)
        cutoff = previous_dt - timedelta(seconds=60) if previous_dt else None
        changed: list[NotionChangeRecord] = []
        for record in records:
            if self.state.page_fingerprints.get(record.key) == record.fingerprint:
                continue
            edited_dt = _parse_iso(record.last_edited_time)
            if cutoff is not None and edited_dt is not None and edited_dt < cutoff:
                continue
            changed.append(record)
        changed.sort(key=lambda item: item.last_edited_time or "", reverse=True)
        return changed[: self.max_items]

    def _scan_with_notion_api(self) -> list[NotionChangeRecord]:
        token = self.auth.get_access_token()
        if not token:
            raise AppAuthError("Notion OAuth token file not found or missing usable access token")
        records: list[NotionChangeRecord] = []
        for object_type in ("page", "database"):
            payload = {
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                "filter": {"property": "object", "value": object_type},
                "page_size": self.max_items,
            }
            response = self._api_post("/search", payload, token)
            results = response.get("results") if isinstance(response, dict) else None
            if not isinstance(results, list):
                continue
            for item in results:
                if isinstance(item, dict):
                    record = _record_from_api_result(item)
                    if record is not None:
                        records.append(record)
        records.sort(key=lambda item: item.last_edited_time or "", reverse=True)
        return records[: self.max_items]

    def _post_notion_api(self, path: str, payload: dict[str, Any], token: str) -> dict[str, Any]:
        current_token = token
        body = ""
        for attempt in range(2):
            req = urlrequest.Request(
                f"{NOTION_API_BASE}{path}",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {current_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Notion-Version": NOTION_API_VERSION,
                    "User-Agent": "truffle-notion-bg/1.0",
                },
                method="POST",
            )
            try:
                with urlrequest.urlopen(req, timeout=30) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    break
            except urlerror.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code in {401, 403}:
                    if attempt == 0:
                        try:
                            current_token = self.auth.refresh_access_token()
                        except Exception as refresh_exc:
                            raise AppAuthError(
                                f"Notion API changelog scan unauthorized: HTTP {exc.code}; refresh failed: {refresh_exc}"
                            ) from refresh_exc
                        continue
                    raise AppAuthError(f"Notion API changelog scan unauthorized: HTTP {exc.code} {body[:300]}") from exc
                raise AppRuntimeFailure(f"Notion API changelog scan failed: HTTP {exc.code} {body[:300]}") from exc
            except Exception as exc:
                raise AppRuntimeFailure(f"Notion API changelog scan failed: {exc}") from exc
        else:
            raise AppRuntimeFailure("Notion API changelog scan failed without a response")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AppRuntimeFailure(f"Notion API returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise AppRuntimeFailure("Notion API returned a non-object payload")
        return parsed

    def _scan_with_mcp_search(self, previous_run: str) -> list[NotionChangeRecord]:
        records: list[NotionChangeRecord] = []
        queries = ["recently edited Notion pages and databases"]
        if previous_run:
            queries.insert(0, f"Notion pages and databases edited since {previous_run}")
        queries.extend(["project", "meeting notes", "tasks", "roadmap"])
        seen_queries: set[str] = set()
        for query in queries:
            if query in seen_queries:
                continue
            seen_queries.add(query)
            result = self._get_client().call_tool("notion_search", {"query": query})
            query_records = self._records_from_mcp_result(result)
            records.extend(query_records)
            if query_records or len(records) >= self.max_items:
                break
            text = _mcp_text(result)
            urls = NOTION_URL_RE.findall(text)
            ids = UUID_RE.findall(text)
            before_text_records = len(records)
            for candidate in (urls or ids)[: self.max_items]:
                try:
                    fetched = self._fetch_candidate(candidate)
                except Exception:
                    continue
                record = self._record_from_mcp_text(candidate, fetched)
                if record is not None:
                    records.append(record)
            if len(records) > before_text_records:
                break
        deduped: dict[str, NotionChangeRecord] = {}
        for record in records:
            deduped[record.key] = record
        return list(deduped.values())[: self.max_items]

    def _records_from_mcp_result(self, result: Any) -> list[NotionChangeRecord]:
        records: list[NotionChangeRecord] = []
        for resource in _mcp_resources(result):
            record = _record_from_mcp_resource(resource)
            if record is not None:
                records.append(record)
        text_json = _json_from_text(_mcp_text(result))
        if text_json is not None:
            for item in _collect_dicts(text_json):
                record = _record_from_mcp_item(item)
                if record is not None:
                    records.append(record)
        for item in _collect_dicts(_mcp_structured(result)):
            record = _record_from_mcp_item(item)
            if record is not None:
                records.append(record)
        deduped: dict[str, NotionChangeRecord] = {}
        for record in records:
            if record.title.lower() in {"notion_search", "success", "notion search results"} and not record.url:
                continue
            if record.key.startswith("mcp-search:"):
                continue
            deduped[record.key] = record
        return list(deduped.values())

    def _workspace_label(self) -> str:
        payload_getter = getattr(self.auth, "get_oauth_payload", None)
        if callable(payload_getter):
            try:
                payload = payload_getter()
            except Exception:
                payload = None
            if isinstance(payload, dict):
                for key in ("workspace_name", "workspace", "workspace_id", "bot_id"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        return _clean_text(value, 100)
                    if isinstance(value, dict):
                        name = _first_str(value, ("name", "display_name", "id"))
                        if name:
                            return _clean_text(name, 100)
        try:
            tools = {_tool_name(tool) for tool in self._get_client().list_tools()}
        except Exception:
            tools = set()
        for tool_name in ("notion_get_self", "notion_users_me", "notion_get_teams", "notion_get_users"):
            if tool_name not in tools:
                continue
            try:
                result = self._get_client().call_tool(tool_name, {})
            except Exception:
                continue
            text = _mcp_text(result)
            parsed = _json_from_text(text)
            if tool_name == "notion_get_teams":
                teams: list[str] = []
                for item in _collect_dicts(parsed if parsed is not None else _mcp_structured(result)):
                    if str(item.get("type") or "") == "team" or "role" in item:
                        name = _first_str(item, ("name", "title", "id"))
                        if name:
                            teams.append(name)
                if teams:
                    return _clean_text(f"{len(teams)} joined Notion teamspace(s): {', '.join(teams[:3])}", 100)
            if tool_name == "notion_get_users":
                for item in _collect_dicts(parsed if parsed is not None else _mcp_structured(result)):
                    name = _first_str(item, ("name", "email", "id"))
                    if name:
                        return _clean_text(f"Notion workspace with {name}", 100)
            for item in _collect_dicts(_mcp_structured(result)):
                name = _first_str(item, ("workspace_name", "workspace", "name", "bot_id", "id"))
                if name:
                    return _clean_text(name, 100)
            if text:
                return _clean_text(text, 100)
        return "unknown"

    def _fetch_candidate(self, candidate: str) -> str:
        result = self._get_client().call_tool("notion_fetch", {"id": candidate})
        return _mcp_text(result)

    def _record_from_mcp_text(self, candidate: str, text: str) -> NotionChangeRecord | None:
        if not text.strip():
            return None
        lines = [line.strip("# -*\t") for line in text.splitlines() if line.strip()]
        title = _clean_text(lines[0] if lines else candidate, 100)
        edited_match = re.search(r"last[_ ]edited[_ ]time[\"': ]+([0-9T:Z+.-]+)", text, re.IGNORECASE)
        by_match = re.search(r"last[_ ]edited[_ ]by[\"': ]+([^,\n}]+)", text, re.IGNORECASE)
        key_match = UUID_RE.search(candidate) or UUID_RE.search(text)
        key = key_match.group(0) if key_match else candidate
        return NotionChangeRecord(
            key=key,
            title=title,
            object_type="page",
            url=candidate if candidate.startswith("http") else "",
            last_edited_time=edited_match.group(1) if edited_match else "",
            last_edited_by=_clean_text(by_match.group(1), 80) if by_match else "unknown",
            fingerprint=digest_hash(text),
        )

    def _build_digest(self, previous_run: str, run_started: str, records: list[NotionChangeRecord], stats: dict[str, Any]) -> str:
        lines = [
            f"Notion changes since {previous_run}: {len(records)} edited page/database item(s).",
            (
                "stats: "
                f"source={stats.get('source')}, scanned={stats.get('scanned')}, changed={stats.get('changed')}, "
                f"workspace={stats.get('workspace') or 'unknown'}, checked_at={run_started}"
            ),
            "Open with notion_fetch(url=...) or notion_fetch(id=...).",
            "",
            "Edited pages/databases:",
        ]
        for record in records:
            open_arg = _notion_fetch_arg(record)
            lines.append(
                "- "
                f"{record.title} ({record.object_type}) edited={record.last_edited_time or 'unknown'} "
                f"by={record.last_edited_by or 'unknown'} target={record.url or record.key} "
                f"open={json.dumps({'tool': 'notion_fetch', 'arguments': open_arg}, separators=(',', ':'))}"
            )
        return "\n".join(lines).strip()

    def _build_baseline_digest(self, run_started: str, records: list[NotionChangeRecord], stats: dict[str, Any]) -> str:
        lines = [
            f"Notion baseline ({run_started[:10]}): {len(records)} recently edited page/database item(s) tracked.",
            (
                "Future Notion background runs will submit only pages or databases that are new or edited after this "
                "baseline scan."
            ),
            (
                "scan: "
                f"source={stats.get('source')}, workspace={stats.get('workspace') or 'unknown'}, "
                f"scanned={stats.get('scanned')}, checked_at={run_started}"
            ),
        ]
        if not records:
            lines.append("No recently edited Notion pages or databases were discovered.")
            return "\n".join(lines).strip()

        lines.append("")
        lines.append("Recently edited pages/databases:")
        for record in records[: self.max_items]:
            target = record.url or record.key
            open_arg = _notion_fetch_arg(record)
            lines.append(
                "- "
                f"{record.title} ({record.object_type}) edited={record.last_edited_time or 'unknown'} "
                f"by={record.last_edited_by or 'unknown'} target={target} "
                f"open={json.dumps({'tool': 'notion_fetch', 'arguments': open_arg}, separators=(',', ':'))}"
            )
        return "\n".join(lines).strip()

    def _load_state(self) -> BackgroundState:
        if not self.state_file.exists():
            return BackgroundState()
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            LOGGER.exception("Failed to read Notion background state; starting fresh")
            return BackgroundState()
        if not isinstance(raw, dict):
            return BackgroundState()
        state = BackgroundState()
        state.last_run_at = str(raw.get("last_run_at", "") or "")
        state.last_digest_at = str(raw.get("last_digest_at", "") or "")
        state.last_digest_hash = str(raw.get("last_digest_hash", "") or "")
        stats = raw.get("last_stats")
        state.last_stats = stats if isinstance(stats, dict) else {}
        fingerprints = raw.get("page_fingerprints")
        state.page_fingerprints = fingerprints if isinstance(fingerprints, dict) else {}
        return state

    def _save_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(asdict(self.state), ensure_ascii=False, indent=2), encoding="utf-8")
