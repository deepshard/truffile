from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from auth import GitHubAuth
from config import GITHUB_API_BASE, MAX_ITEMS_PER_QUERY, MAX_ORGS_TO_SCAN


@dataclass(frozen=True)
class GitHubWorkItem:
    id: int
    number: int
    title: str
    repo: str
    html_url: str
    updated_at: str
    author: str


@dataclass(frozen=True)
class SearchResult:
    total_count: int
    items: list[GitHubWorkItem]


@dataclass(frozen=True)
class OrgActivity:
    org: str
    issue_count: int
    pr_count: int


@dataclass(frozen=True)
class CycleResult:
    summary: str | None
    uris: list[str]
    priority: int
    changed: bool
    auth_error: str | None = None
    error: str | None = None


class GitHubAuthError(RuntimeError):
    pass


def is_hard_auth_failure(message: str) -> bool:
    text = (message or "").lower()
    hard_markers = (
        "bad credentials",
        "invalid token",
        "oauth token file not found",
        "missing access_token",
        "access denied",
        "requires authentication",
    )
    return any(marker in text for marker in hard_markers)


class GitHubBackgroundWorker:
    def __init__(self) -> None:
        self._last_fingerprint: str | None = None
        self._auth = GitHubAuth(read_only=True)

    def close(self) -> None:
        # This worker currently creates per-request transports only, but the
        # background shell closes it before each checkpointed cycle so future
        # client/session state is not accidentally reused after restore.
        return None

    def verify(self) -> tuple[bool, str]:
        try:
            token = self._load_access_token()
            login = self._fetch_user_login(token)
            return True, f"GitHub background verify OK (user=@{login})"
        except Exception as exc:
            return False, str(exc)

    def run_cycle(self) -> CycleResult:
        try:
            token = self._load_access_token()
            login = self._fetch_user_login(token)
            orgs = self._fetch_orgs(token)

            review_requested = self._search(
                token,
                f"is:open is:pr review-requested:{login} archived:false sort:updated-desc",
            )
            authored_prs = self._search(
                token,
                f"is:open is:pr author:{login} archived:false sort:updated-desc",
            )
            involved_issues = self._search(
                token,
                f"is:open is:issue involves:{login} archived:false sort:updated-desc",
            )

            org_activity = self._fetch_org_activity(token, login, orgs)
            fingerprint = self._make_fingerprint(
                login=login,
                review_requested=review_requested,
                authored_prs=authored_prs,
                involved_issues=involved_issues,
                org_activity=org_activity,
            )
            if self._last_fingerprint == fingerprint:
                return CycleResult(summary=None, uris=[], priority=0, changed=False)

            self._last_fingerprint = fingerprint
            summary, uris = self._build_digest(
                login=login,
                review_requested=review_requested,
                authored_prs=authored_prs,
                involved_issues=involved_issues,
                orgs=orgs,
                org_activity=org_activity,
            )
            priority = 1 if review_requested.total_count > 0 or involved_issues.total_count > 0 else 0
            return CycleResult(summary=summary, uris=uris, priority=priority, changed=True)
        except GitHubAuthError as exc:
            return CycleResult(summary=None, uris=[], priority=0, changed=False, auth_error=str(exc))
        except Exception as exc:
            return CycleResult(summary=None, uris=[], priority=0, changed=False, error=str(exc))

    def _load_access_token(self) -> str:
        try:
            return self._auth.load_access_token()
        except Exception as exc:
            raise GitHubAuthError(str(exc)) from exc

    def _fetch_user_login(self, token: str) -> str:
        payload = self._request_json("/user", token=token)
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected /user response shape")
        login = str(payload.get("login", "") or "").strip()
        if not login:
            raise RuntimeError("Unable to determine GitHub user login")
        return login

    def _fetch_orgs(self, token: str) -> list[str]:
        payload = self._request_json("/user/orgs", token=token, query={"per_page": "100"})
        if not isinstance(payload, list):
            return []
        orgs: list[str] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            login = str(item.get("login", "") or "").strip()
            if login:
                orgs.append(login)
        return sorted(set(orgs))

    def _fetch_org_activity(self, token: str, login: str, orgs: list[str]) -> list[OrgActivity]:
        activity: list[OrgActivity] = []
        for org in orgs[:MAX_ORGS_TO_SCAN]:
            issue_result = self._search(
                token,
                f"org:{org} is:open is:issue involves:{login} archived:false sort:updated-desc",
                per_page=3,
            )
            pr_result = self._search(
                token,
                f"org:{org} is:open is:pr involves:{login} archived:false sort:updated-desc",
                per_page=3,
            )
            if issue_result.total_count == 0 and pr_result.total_count == 0:
                continue
            activity.append(OrgActivity(org=org, issue_count=issue_result.total_count, pr_count=pr_result.total_count))
        return activity

    def _search(self, token: str, query: str, *, per_page: int = MAX_ITEMS_PER_QUERY) -> SearchResult:
        payload = self._request_json(
            "/search/issues",
            token=token,
            query={"q": query, "sort": "updated", "order": "desc", "per_page": str(per_page)},
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected search response shape")

        total_count = int(payload.get("total_count") or 0)
        raw_items = payload.get("items")
        items: list[GitHubWorkItem] = []
        if isinstance(raw_items, list):
            for raw in raw_items[:per_page]:
                parsed = self._parse_search_item(raw)
                if parsed is not None:
                    items.append(parsed)
        return SearchResult(total_count=total_count, items=items)

    def _parse_search_item(self, raw: Any) -> GitHubWorkItem | None:
        if not isinstance(raw, dict):
            return None
        item_id = int(raw.get("id") or 0)
        number = int(raw.get("number") or 0)
        title = str(raw.get("title", "") or "").strip()
        html_url = str(raw.get("html_url", "") or "").strip()
        updated_at = str(raw.get("updated_at", "") or "").strip()
        user_obj = raw.get("user")
        author = str(user_obj.get("login", "") or "").strip() if isinstance(user_obj, dict) else ""
        repo = self._repo_from_repository_url(str(raw.get("repository_url", "") or ""))
        if not item_id or not number or not title:
            return None
        return GitHubWorkItem(
            id=item_id,
            number=number,
            title=title,
            repo=repo or "?/?",
            html_url=html_url,
            updated_at=updated_at,
            author=author or "?",
        )

    @staticmethod
    def _repo_from_repository_url(repository_url: str) -> str:
        clean = (repository_url or "").strip().rstrip("/")
        if "/repos/" not in clean:
            return ""
        return clean.split("/repos/", 1)[-1]

    def _request_json(self, path: str, *, token: str, query: dict[str, str] | None = None) -> Any:
        url = f"{GITHUB_API_BASE}{path}"
        if query:
            url = f"{url}?{urlparse.urlencode(query)}"

        req = urlrequest.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "truffle-github-bg/1.0",
            },
        )
        try:
            with urlrequest.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if resp.status in {401, 403}:
                    raise GitHubAuthError(f"GitHub API returned {resp.status}: unauthorized")
                if resp.status >= 400:
                    raise RuntimeError(f"GitHub API returned {resp.status}: {raw[:300]}")
        except urlerror.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {401, 403}:
                detail = self._extract_api_error(body) or f"GitHub API returned {exc.code}"
                if exc.code == 403 and "rate limit" in detail.lower():
                    raise RuntimeError(detail) from exc
                raise GitHubAuthError(detail) from exc
            raise RuntimeError(f"GitHub API error {exc.code}: {body[:300]}") from exc
        except GitHubAuthError:
            raise
        except Exception as exc:
            raise RuntimeError(f"GitHub API request failed: {exc}") from exc

        try:
            return json.loads(raw)
        except Exception as exc:
            raise RuntimeError(f"GitHub API returned invalid JSON: {exc}") from exc

    @staticmethod
    def _extract_api_error(raw: str) -> str:
        text = (raw or "").strip()
        if not text:
            return ""
        try:
            payload = json.loads(text)
        except Exception:
            return text[:200]
        if isinstance(payload, dict):
            message = str(payload.get("message", "") or "").strip()
            if message:
                return f"GitHub auth error: {message}"
        return text[:200]

    def _make_fingerprint(
        self,
        *,
        login: str,
        review_requested: SearchResult,
        authored_prs: SearchResult,
        involved_issues: SearchResult,
        org_activity: list[OrgActivity],
    ) -> str:
        material = {
            "login": login,
            "review_requested_total": review_requested.total_count,
            "authored_pr_total": authored_prs.total_count,
            "involved_issue_total": involved_issues.total_count,
            "review_requested_ids": [item.id for item in review_requested.items],
            "authored_pr_ids": [item.id for item in authored_prs.items],
            "involved_issue_ids": [item.id for item in involved_issues.items],
            "org_activity": [
                {"org": row.org, "issues": row.issue_count, "prs": row.pr_count}
                for row in org_activity
            ],
        }
        blob = json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def _build_digest(
        self,
        *,
        login: str,
        review_requested: SearchResult,
        authored_prs: SearchResult,
        involved_issues: SearchResult,
        orgs: list[str],
        org_activity: list[OrgActivity],
    ) -> tuple[str, list[str]]:
        now_iso = datetime.now(UTC).replace(microsecond=0).isoformat()
        lines = [
            f"GitHub activity digest ({now_iso}) for @{login}",
            "",
            "Action queue:",
            f"- PRs waiting for your review: {review_requested.total_count}",
            f"- Your open PRs: {authored_prs.total_count}",
            f"- Open issues involving you: {involved_issues.total_count}",
            "",
        ]

        uris: list[str] = []
        self._append_items(lines, "Top PRs waiting for your review", review_requested.items, uris=uris)
        self._append_items(lines, "Top open issues involving you", involved_issues.items, uris=uris)
        self._append_items(lines, "Top open PRs authored by you", authored_prs.items, uris=uris)

        if orgs:
            preview = ", ".join(orgs[:8])
            if len(orgs) > 8:
                preview += f", +{len(orgs) - 8} more"
            lines.append(f"Organization access: {len(orgs)} org(s) visible ({preview}).")
            if len(orgs) > MAX_ORGS_TO_SCAN:
                lines.append(
                    f"Org activity scan currently limited to first {MAX_ORGS_TO_SCAN} org(s). "
                    "Set GITHUB_BG_MAX_ORGS to raise this."
                )
        else:
            lines.append("Organization access: no org memberships visible to this token.")

        if org_activity:
            lines.append("")
            lines.append("Org activity where this token has access:")
            for row in org_activity:
                lines.append(
                    f"- {row.org}: {row.issue_count} open issue(s), {row.pr_count} open PR(s) involving you"
                )

        lines.extend(
            [
                "",
                "Suggested next actions:",
                "- Ask Codex or another coding app to investigate the highest-priority item and propose a plan.",
                "- Useful GitHub MCP tools: list_issues/search_issues, list_pull_requests/pull_request_read, issue_write, pull_request_review_write, update_pull_request, merge_pull_request.",
                "- Prompt template: \"Based on the GitHub digest above, pick the highest-priority item and propose an execution plan before making changes.\"",
            ]
        )
        return "\n".join(lines).strip(), list(dict.fromkeys(u for u in uris if u))

    @staticmethod
    def _append_items(
        lines: list[str],
        heading: str,
        items: list[GitHubWorkItem],
        *,
        uris: list[str],
        max_items: int = 4,
    ) -> None:
        lines.append(heading + ":")
        if not items:
            lines.append("- None")
            lines.append("")
            return
        for item in items[:max_items]:
            short_title = " ".join(item.title.split())
            if len(short_title) > 120:
                short_title = short_title[:119] + "..."
            lines.append(
                f"- {item.repo}#{item.number}: {short_title} (author=@{item.author}, updated={item.updated_at})"
            )
            if item.html_url:
                uris.append(item.html_url)
        lines.append("")
