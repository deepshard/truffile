from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timezone
import logging
from typing import Any

import arxiv

from arxiv_common import get_bg_state_path, parse_research_interests

logger = logging.getLogger("arxiv.bg_worker")
logger.setLevel(logging.INFO)


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
    error: str | None = None


class ArxivBackgroundWorker:
    def __init__(self, interests_raw: str) -> None:
        self._interests_raw = interests_raw
        self._client = arxiv.Client()
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
        recommendations: list[ArxivRecommendation] = []

        for interest in interests:
            for paper in self._search_interest(interest, max_results=8):
                paper_id = paper.get_short_id()
                if not paper_id or paper_id in seen_ids:
                    continue
                published_iso = paper.published.astimezone(timezone.utc).date().isoformat()
                recommendations.append(
                    ArxivRecommendation(
                        interest=interest,
                        paper_id=paper_id,
                        title=paper.title.strip(),
                        published=published_iso,
                        abs_url=f"https://arxiv.org/abs/{paper_id}",
                        summary=" ".join((paper.summary or "").split())[:450],
                    )
                )
                seen_ids.add(paper_id)
                if len(recommendations) >= 3:
                    break
            if len(recommendations) >= 3:
                break

        if not recommendations:
            return BgRunResult(content=None)

        state["seen_ids"] = sorted(list(seen_ids))[-1500:]
        self._save_state(state)
        return BgRunResult(content=self._build_context(recommendations))

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
                return {"seen_ids": []}
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception as exc:
            logger.warning("Failed to load BG state: %s", exc)
        return {"seen_ids": []}

    def _save_state(self, state: dict[str, Any]) -> None:
        path = self._state_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:
            logger.warning("Failed to save BG state: %s", exc)

    def _build_context(self, items: list[ArxivRecommendation]) -> str:
        lines: list[str] = [
            "These are research papers the user likes.",
            "Please use a research tool like Exa or web search to read each paper and provide the user a summary and notes.",
            "",
            "Recommended papers:",
        ]
        for idx, item in enumerate(items, start=1):
            lines.append(
                f"{idx}. {item.title} (arXiv:{item.paper_id}, published {item.published})"
            )
            lines.append(f"   Interest match: {item.interest}")
            lines.append(f"   URL: {item.abs_url}")
            if item.summary:
                lines.append(f"   Abstract snippet: {item.summary}")
        return "\n".join(lines)
