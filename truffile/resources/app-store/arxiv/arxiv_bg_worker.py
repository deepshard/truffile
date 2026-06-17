from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
import logging
from typing import Any

import arxiv

from arxiv_common import get_bg_state_path, parse_research_interests

logger = logging.getLogger("arxiv.bg_worker")
logger.setLevel(logging.INFO)

DEFAULT_MAX_PAPERS_PER_RUN = 2
DEFAULT_SEARCH_RESULTS_PER_INTEREST = 5
DEFAULT_INTERESTS_PER_RUN = 1
MAX_SEEN_IDS = 3000


@dataclass
class ArxivRecommendation:
    interest: str
    paper_id: str
    title: str
    published: str
    abs_url: str
    summary: str


@dataclass
class BgRunResult:
    content: str | None = None
    uris: list[str] = field(default_factory=list)
    error: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)


class ArxivBackgroundWorker:
    def __init__(self, interests_raw: str) -> None:
        self._interests_raw = interests_raw
        self._client = self._make_client()
        self._state_path = get_bg_state_path()

    @property
    def interests(self) -> list[str]:
        return parse_research_interests(self._interests_raw)

    def verify(self) -> tuple[bool, str]:
        interests = self.interests
        if not interests:
            return False, "No research interests configured. Provide at least one interest."
        return True, f"ArXiv background configured with {len(interests)} interest(s)."

    def run_cycle(self) -> BgRunResult:
        interests = self.interests
        if not interests:
            return BgRunResult(error="no_interests")

        state = self._load_state()
        seen_ids: set[str] = set(state.get("seen_ids") or [])
        seeded = bool(state.get("initialized_at"))
        recommendations: list[ArxivRecommendation] = []
        max_papers = self._env_int("ARXIV_BG_MAX_PAPERS_PER_RUN", DEFAULT_MAX_PAPERS_PER_RUN)
        search_results = self._env_int("ARXIV_BG_SEARCH_RESULTS_PER_INTEREST", DEFAULT_SEARCH_RESULTS_PER_INTEREST)
        interests_per_run = min(
            len(interests),
            self._env_int("ARXIV_BG_INTERESTS_PER_RUN", DEFAULT_INTERESTS_PER_RUN),
        )
        selected_interests, next_interest_index = self._select_interests(
            interests,
            start_index=self._state_int(state, "next_interest_index", 0),
            count=interests_per_run,
        )
        scanned_ids: set[str] = set()

        for interest in selected_interests:
            for paper in self._search_interest(interest, max_results=search_results):
                paper_id = paper.get_short_id()
                seen_key = self._seen_key(paper_id)
                if not paper_id or not seen_key:
                    continue
                scanned_ids.add(seen_key)
                if seen_key in seen_ids:
                    continue
                seen_ids.add(seen_key)
                if not seeded:
                    continue
                if len(recommendations) >= max_papers:
                    continue
                published_iso = paper.published.astimezone(timezone.utc).date().isoformat()
                recommendations.append(
                    ArxivRecommendation(
                        interest=interest,
                        paper_id=paper_id,
                        title=paper.title.strip(),
                        published=published_iso,
                        abs_url=f"https://arxiv.org/abs/{paper_id}",
                        summary=" ".join((paper.summary or "").split())[:180],
                    )
                )

        now = datetime.now(UTC).replace(microsecond=0).isoformat()
        state["seen_ids"] = sorted(list(seen_ids))[-MAX_SEEN_IDS:]
        state["next_interest_index"] = next_interest_index
        state["last_run_at"] = now
        if not seeded:
            state["initialized_at"] = now
        self._save_state(state)

        stats = {
            "baseline_seeded": not seeded,
            "interests_scanned": selected_interests,
            "search_results_per_interest": search_results,
            "papers_scanned": len(scanned_ids),
            "papers": len(recommendations),
        }

        if not recommendations:
            return BgRunResult(
                content=None,
                stats=stats,
            )

        return BgRunResult(
            content=self._build_context(recommendations),
            uris=self._paper_uris(recommendations),
            stats=stats,
        )

    @staticmethod
    def _make_client() -> arxiv.Client:
        try:
            return arxiv.Client(
                page_size=DEFAULT_SEARCH_RESULTS_PER_INTEREST,
                delay_seconds=0.0,
                num_retries=0,
            )
        except TypeError:
            return arxiv.Client()

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        try:
            return max(1, int(os.getenv(name, str(default)).strip()))
        except ValueError:
            return default

    @staticmethod
    def _state_int(state: dict[str, Any], key: str, default: int) -> int:
        try:
            return max(0, int(state.get(key, default)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _select_interests(interests: list[str], *, start_index: int, count: int) -> tuple[list[str], int]:
        if not interests:
            return [], 0
        count = max(1, min(count, len(interests)))
        start = start_index % len(interests)
        selected = [interests[(start + offset) % len(interests)] for offset in range(count)]
        return selected, (start + count) % len(interests)

    @staticmethod
    def _seen_key(paper_id: str) -> str:
        return re.sub(r"v\d+$", "", str(paper_id or "").strip())

    def _search_interest(self, interest: str, *, max_results: int) -> list[arxiv.Result]:
        try:
            search = arxiv.Search(
                query=interest,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
            )
            return list(self._client.results(search))
        except Exception as exc:
            logger.warning("arXiv search failed for interest '%s': %s", interest, exc)
            return []

    def _load_state(self) -> dict[str, Any]:
        path = self._state_path
        try:
            if not path.exists():
                return {"seen_ids": [], "next_interest_index": 0}
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as exc:
            logger.warning("Failed to load BG state: %s", exc)
        return {"seen_ids": [], "next_interest_index": 0}

    def _save_state(self, state: dict[str, Any]) -> None:
        path = self._state_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to save BG state: %s", exc)

    def _build_context(
        self,
        items: list[ArxivRecommendation],
    ) -> str:
        lines: list[str] = [f"arXiv notification delta: {len(items)} new paper(s)."]
        for item in items:
            lines.append(f"- {item.title} ({item.paper_id}, published {item.published})")
            lines.append(f"  why: matches research interest '{item.interest}'")
            lines.append(f"  open: download_paper paper_id=\"{item.paper_id}\"")
            lines.append(f"  url: {item.abs_url}")
        return "\n".join(lines)

    @staticmethod
    def _paper_uris(items: list[ArxivRecommendation]) -> list[str]:
        uris: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item.abs_url and item.abs_url not in seen:
                uris.append(item.abs_url)
                seen.add(item.abs_url)
        return uris
