from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import xml.etree.ElementTree as et
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

import arxiv
import httpx
from pypdf import PdfReader

from arxiv_common import MAX_RESULTS, get_storage_path

logger = logging.getLogger("arxiv.tools")
logger.setLevel(logging.INFO)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
DEFAULT_RETRY_AFTER_SECONDS = 300
ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

VALID_CATEGORIES = {
    "cs",
    "econ",
    "eess",
    "math",
    "physics",
    "q-bio",
    "q-fin",
    "stat",
    "astro-ph",
    "cond-mat",
    "gr-qc",
    "hep-ex",
    "hep-lat",
    "hep-ph",
    "hep-th",
    "math-ph",
    "nlin",
    "nucl-ex",
    "nucl-th",
    "quant-ph",
}


@dataclass
class ConversionStatus:
    paper_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


_conversion_statuses: dict[str, ConversionStatus] = {}
_SLASH_TOKEN = "__arxiv_slash__"
_ARXIV_API_LOCK = asyncio.Lock()
_LAST_ARXIV_API_CALL_AT = 0.0


class PaperNotFoundError(Exception):
    pass


def _pdf_url_for_paper_id(paper_id: str) -> str:
    return f"https://arxiv.org/pdf/{paper_id}"


def _request_interval_seconds() -> float:
    raw = os.getenv("ARXIV_REQUEST_INTERVAL_SECONDS", "3")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 3.0


def _rate_limit_retry_attempts() -> int:
    raw = os.getenv("ARXIV_RATE_LIMIT_MAX_ATTEMPTS", "3")
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def _rate_limit_retry_delay_seconds(exc: Exception) -> float:
    raw = os.getenv("ARXIV_RATE_LIMIT_RETRY_SECONDS", "")
    if raw.strip():
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return min(float(_retry_after_seconds(exc)), 3.0)


def _with_common_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


async def _run_live_arxiv_call(action: Callable[[], Awaitable[Any]]) -> Any:
    global _LAST_ARXIV_API_CALL_AT
    async with _ARXIV_API_LOCK:
        attempts = _rate_limit_retry_attempts()
        for attempt in range(attempts):
            interval = _request_interval_seconds()
            elapsed = time.monotonic() - _LAST_ARXIV_API_CALL_AT
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)
            try:
                result = await action()
                _LAST_ARXIV_API_CALL_AT = time.monotonic()
                return result
            except Exception as exc:
                _LAST_ARXIV_API_CALL_AT = time.monotonic()
                if not _is_rate_limit_error(exc) or attempt + 1 >= attempts:
                    raise
                await asyncio.sleep(_rate_limit_retry_delay_seconds(exc))

        raise RuntimeError("unreachable arXiv retry state")


def _retry_after_seconds(exc: Exception) -> int:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after:
        try:
            return max(1, int(float(retry_after)))
        except ValueError:
            pass
    return DEFAULT_RETRY_AFTER_SECONDS


def _is_rate_limit_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "ratelimit" in text or "too many requests" in text


def _rate_limited_response(*, operation: str, exc: Exception, paper_id: str | None = None) -> dict[str, Any]:
    retry_after = _retry_after_seconds(exc)
    attempts = _rate_limit_retry_attempts()
    payload: dict[str, Any] = {
        "status": "rate_limited",
        "message": f"arXiv rate-limited {operation} after {attempts} attempts. Wait before retrying.",
        "retry_after_seconds": retry_after,
        "attempts": attempts,
    }
    if paper_id:
        payload.update(_local_paper_hints(paper_id))
    return payload


def _normalize_categories(categories: list[str] | str | None) -> list[str] | None:
    if categories is None:
        return None
    if isinstance(categories, str):
        raw = categories.strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = [part.strip() for part in raw.split(",")]
        if isinstance(parsed, list):
            return [str(part).strip() for part in parsed if str(part).strip()]
        return [raw]
    return [str(part).strip() for part in categories if str(part).strip()]


def _safe_paper_filename(paper_id: str) -> str:
    return paper_id.replace("/", _SLASH_TOKEN)


def _get_paper_path(paper_id: str, suffix: str = ".md") -> Path:
    storage = get_storage_path()
    storage.mkdir(parents=True, exist_ok=True)
    return storage / f"{_safe_paper_filename(paper_id)}{suffix}"


def _local_paper_hints(paper_id: str, suffix: str = ".md") -> dict[str, Any]:
    path = _get_paper_path(paper_id, suffix)
    return {
        "paper_id": paper_id,
        "exists": path.exists(),
        "path": str(path),
        "resource_uri": path.as_uri(),
    }


def list_stored_paper_ids() -> list[str]:
    storage = get_storage_path()
    ids: list[str] = []
    for path in storage.glob("*.md"):
        ids.append(path.stem.replace(_SLASH_TOKEN, "/"))
    return ids


def _strip_arxiv_version(paper_id: str) -> str:
    head, marker, tail = paper_id.rpartition("v")
    if marker and tail.isdigit() and head:
        return head
    return paper_id


def _stored_paper_id_for_result(result_paper_id: str, stored_ids: list[str]) -> str:
    if result_paper_id in stored_ids:
        return result_paper_id
    result_base = _strip_arxiv_version(result_paper_id)
    for stored_id in stored_ids:
        if _strip_arxiv_version(stored_id) == result_base:
            return stored_id
    return result_paper_id


def _validate_categories(categories: list[str]) -> bool:
    for category in categories:
        prefix = category.split(".", 1)[0] if "." in category else category
        if prefix not in VALID_CATEGORIES:
            logger.warning("Unknown category prefix: %s", prefix)
            return False
    return True


def _optimize_query(query: str) -> str:
    if any(field in query for field in ["ti:", "au:", "abs:", "cat:", "AND", "OR", "ANDNOT"]):
        return query
    if query.startswith('"') and query.endswith('"'):
        return query
    return query


def _parse_arxiv_atom_response(xml_text: str, *, include_abstracts: bool = False) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    try:
        root = et.fromstring(xml_text)
    except et.ParseError as exc:
        raise ValueError(f"Failed to parse arXiv API response: {exc}") from exc

    for entry in root.findall("atom:entry", ARXIV_NS):
        id_elem = entry.find("atom:id", ARXIV_NS)
        if id_elem is None or not id_elem.text:
            continue

        paper_id = id_elem.text.split("/abs/")[-1]
        short_id = paper_id.split("v", 1)[0] if "v" in paper_id else paper_id

        title_elem = entry.find("atom:title", ARXIV_NS)
        title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else ""

        authors: list[str] = []
        for author in entry.findall("atom:author", ARXIV_NS):
            name_elem = author.find("atom:name", ARXIV_NS)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text)

        summary_elem = entry.find("atom:summary", ARXIV_NS)
        abstract = summary_elem.text.strip().replace("\n", " ") if summary_elem is not None and summary_elem.text else ""

        categories: list[str] = []
        for cat in entry.findall("arxiv:primary_category", ARXIV_NS):
            term = cat.get("term")
            if term:
                categories.append(term)
        for cat in entry.findall("atom:category", ARXIV_NS):
            term = cat.get("term")
            if term and term not in categories:
                categories.append(term)

        published_elem = entry.find("atom:published", ARXIV_NS)
        published = published_elem.text if published_elem is not None and published_elem.text else ""

        updated_elem = entry.find("atom:updated", ARXIV_NS)
        updated = updated_elem.text if updated_elem is not None and updated_elem.text else ""

        paper = {
            "paper_id": short_id,
            "title": title,
            "authors": authors,
            "categories": categories,
            "published": published,
            "updated": updated,
            "url": f"https://arxiv.org/abs/{short_id}",
        }
        if include_abstracts:
            paper["abstract"] = abstract
        results.append(paper)

    return results


def _format_arxiv_submitted_date(value: str, suffix: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid date format. Use YYYY-MM-DD format: {exc}") from exc
    return parsed.strftime("%Y%m%d") + suffix


async def _raw_arxiv_search(
    *,
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
    date_from: str | None = None,
    date_to: str | None = None,
    categories: list[str] | None = None,
    include_abstracts: bool = False,
) -> list[dict[str, Any]]:
    query_parts: list[str] = []

    if query.strip():
        query_parts.append(f"({query})")

    if categories:
        category_filter = " OR ".join(f"cat:{cat}" for cat in categories)
        query_parts.append(f"({category_filter})")

    if date_from or date_to:
        try:
            start_date = _format_arxiv_submitted_date(date_from, "0000") if date_from else "199107010000"
            end_date = _format_arxiv_submitted_date(date_to, "2359") if date_to else datetime.now().strftime("%Y%m%d2359")
        except (ValueError, TypeError) as exc:
            raise ValueError(str(exc)) from exc
        query_parts.append(f"submittedDate:[{start_date}+TO+{end_date}]")

    if not query_parts:
        raise ValueError("No search criteria provided")

    final_query = " AND ".join(query_parts)
    sort_map = {
        "relevance": "relevance",
        "date": "submittedDate",
        "submittedDate": "submittedDate",
        "submitted_date": "submittedDate",
    }
    encoded_query = final_query.replace(" AND ", "+AND+").replace(" OR ", "+OR+").replace(" ", "+")
    url = (
        f"{ARXIV_API_URL}?search_query={encoded_query}"
        f"&max_results={max_results}"
        f"&sortBy={sort_map.get(sort_by, 'relevance')}"
        "&sortOrder=descending"
    )

    async def _fetch() -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response

    response = await _run_live_arxiv_call(_fetch)
    return _parse_arxiv_atom_response(response.text, include_abstracts=include_abstracts)


def _process_paper(paper: arxiv.Result, *, include_abstracts: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "paper_id": paper.get_short_id(),
        "title": paper.title,
        "authors": [author.name for author in paper.authors],
        "categories": paper.categories,
        "published": paper.published.isoformat(),
        "updated": paper.updated.isoformat() if paper.updated else "",
        "url": f"https://arxiv.org/abs/{paper.get_short_id()}",
    }
    if include_abstracts:
        payload["abstract"] = paper.summary
    return payload


async def search_papers(
    *,
    query: str,
    max_results: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
    categories: list[str] | None = None,
    sort_by: str = "relevance",
    include_abstracts: bool = False,
) -> dict[str, Any]:
    try:
        bounded_max = min(int(max_results), MAX_RESULTS)
        categories = _normalize_categories(categories)
        if categories and not _validate_categories(categories):
            return _with_common_metadata({"status": "error", "message": "Invalid category provided. Please check arXiv category names."})

        if date_from or date_to:
            results = await _raw_arxiv_search(
                query=_optimize_query(query) if query.strip() else "",
                max_results=bounded_max,
                sort_by=sort_by,
                date_from=date_from,
                date_to=date_to,
                categories=categories,
                include_abstracts=include_abstracts,
            )
            return _with_common_metadata({"status": "success", "total_results": len(results), "papers": results})

        query_parts: list[str] = []
        if query.strip():
            query_parts.append(f"({_optimize_query(query)})")
        if categories:
            query_parts.append("(" + " OR ".join(f"cat:{cat}" for cat in categories) + ")")
        if not query_parts:
            return _with_common_metadata({"status": "error", "message": "No search criteria provided"})

        final_query = " ".join(query_parts)
        sort_criterion = (
            arxiv.SortCriterion.SubmittedDate
            if sort_by in {"date", "submittedDate", "submitted_date"}
            else arxiv.SortCriterion.Relevance
        )
        search = arxiv.Search(query=final_query, max_results=bounded_max, sort_by=sort_criterion)

        def _search_with_client() -> list[dict[str, Any]]:
            client = arxiv.Client()
            papers: list[dict[str, Any]] = []
            for paper in client.results(search):
                if len(papers) >= bounded_max:
                    break
                papers.append(_process_paper(paper, include_abstracts=include_abstracts))
            return papers

        async def _call() -> list[dict[str, Any]]:
            return await asyncio.to_thread(_search_with_client)

        papers = await _run_live_arxiv_call(_call)
        return _with_common_metadata({"status": "success", "total_results": len(papers), "papers": papers})
    except httpx.HTTPStatusError as exc:
        if _is_rate_limit_error(exc):
            return _rate_limited_response(operation="search_papers", exc=exc)
        return _with_common_metadata({"status": "error", "message": f"arXiv HTTP error - {exc}"})
    except arxiv.ArxivError as exc:
        if _is_rate_limit_error(exc):
            return _rate_limited_response(operation="search_papers", exc=exc)
        return _with_common_metadata({"status": "error", "message": f"ArXiv API error - {exc}"})
    except Exception as exc:
        if _is_rate_limit_error(exc):
            return _rate_limited_response(operation="search_papers", exc=exc)
        return _with_common_metadata({"status": "error", "message": str(exc)})


def _convert_pdf_to_markdown(paper_id: str, pdf_path: Path) -> None:
    try:
        reader = PdfReader(str(pdf_path))
        chunks: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            chunks.append(f"# Page {index}\n\n{text.strip()}\n")
        markdown = "\n".join(chunks).strip()
        if not markdown:
            markdown = "No extractable text found in PDF."
        md_path = _get_paper_path(paper_id, ".md")
        md_path.write_text(markdown, encoding="utf-8")
        status = _conversion_statuses.get(paper_id)
        if status:
            status.status = "success"
            status.completed_at = datetime.now()
        try:
            pdf_path.unlink(missing_ok=True)
        except Exception:
            pass
    except Exception as exc:
        status = _conversion_statuses.get(paper_id)
        if status:
            status.status = "error"
            status.completed_at = datetime.now()
            status.error = str(exc)


async def download_paper(*, paper_id: str, check_status: bool = False) -> dict[str, Any]:
    try:
        if check_status:
            status = _conversion_statuses.get(paper_id)
            if not status:
                if _get_paper_path(paper_id, ".md").exists():
                    return _with_common_metadata({
                        "status": "success",
                        "message": "Paper is ready",
                        **_local_paper_hints(paper_id),
                    })
                return _with_common_metadata({
                    "status": "unknown",
                    "message": "No download or conversion in progress",
                    **_local_paper_hints(paper_id),
                })
            return _with_common_metadata({
                "paper_id": paper_id,
                "status": status.status,
                "started_at": status.started_at.isoformat(),
                "completed_at": status.completed_at.isoformat() if status.completed_at else None,
                "error": status.error,
                "message": f"Paper conversion {status.status}",
                **_local_paper_hints(paper_id),
            })

        if _get_paper_path(paper_id, ".md").exists():
            return _with_common_metadata({
                "status": "success",
                "message": "Paper already available",
                **_local_paper_hints(paper_id),
            })

        if paper_id in _conversion_statuses:
            status = _conversion_statuses[paper_id]
            return _with_common_metadata({
                "status": status.status,
                "message": f"Paper conversion {status.status}",
                "started_at": status.started_at.isoformat(),
                **_local_paper_hints(paper_id),
            })

        _conversion_statuses[paper_id] = ConversionStatus(
            paper_id=paper_id,
            status="downloading",
            started_at=datetime.now(),
        )

        pdf_path = _get_paper_path(paper_id, ".pdf")

        async def _call() -> None:
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(_pdf_url_for_paper_id(paper_id))
            if response.status_code == 404:
                raise PaperNotFoundError(paper_id)
            response.raise_for_status()
            pdf_path.write_bytes(response.content)

        await _run_live_arxiv_call(_call)

        status = _conversion_statuses[paper_id]
        status.status = "converting"
        asyncio.create_task(asyncio.to_thread(_convert_pdf_to_markdown, paper_id, pdf_path))
        return _with_common_metadata({
            "paper_id": paper_id,
            "status": "converting",
            "message": "Paper downloaded, conversion started",
            "started_at": status.started_at.isoformat(),
            **_local_paper_hints(paper_id),
        })
    except PaperNotFoundError:
        status = _conversion_statuses.get(paper_id)
        if status:
            status.status = "not_found"
            status.completed_at = datetime.now()
            status.error = f"Paper {paper_id} not found on arXiv"
        _get_paper_path(paper_id, ".pdf").unlink(missing_ok=True)
        return _with_common_metadata({
            "status": "not_found",
            "message": f"Paper {paper_id} not found on arXiv",
            "next_action": "check the arXiv ID or use search_papers to find the correct paper",
            **_local_paper_hints(paper_id),
        })
    except arxiv.ArxivError as exc:
        status = _conversion_statuses.get(paper_id)
        if status:
            status.status = "rate_limited" if _is_rate_limit_error(exc) else "failed"
            status.completed_at = datetime.now()
            status.error = str(exc)
        _get_paper_path(paper_id, ".pdf").unlink(missing_ok=True)
        if _is_rate_limit_error(exc):
            return _rate_limited_response(operation="download_paper", exc=exc, paper_id=paper_id)
        return _with_common_metadata({"status": "failed", "message": f"ArXiv API error - {exc}", **_local_paper_hints(paper_id)})
    except Exception as exc:
        status = _conversion_statuses.get(paper_id)
        if status:
            status.status = "rate_limited" if _is_rate_limit_error(exc) else "failed"
            status.completed_at = datetime.now()
            status.error = str(exc)
        _get_paper_path(paper_id, ".pdf").unlink(missing_ok=True)
        if _is_rate_limit_error(exc):
            return _rate_limited_response(operation="download_paper", exc=exc, paper_id=paper_id)
        return _with_common_metadata({"status": "failed", "message": f"Error: {exc}", **_local_paper_hints(paper_id)})


async def check_paper_status(*, paper_id: str) -> dict[str, Any]:
    return await download_paper(paper_id=paper_id, check_status=True)


async def list_papers(*, include_abstracts: bool = False) -> dict[str, Any]:
    try:
        paper_ids = list_stored_paper_ids()
        if not paper_ids:
            return _with_common_metadata({"status": "success", "total_papers": 0, "papers": []})

        def _list_with_client() -> list[dict[str, Any]]:
            client = arxiv.Client()
            results = client.results(arxiv.Search(id_list=paper_ids))
            papers: list[dict[str, Any]] = []
            for result in results:
                arxiv_paper_id = result.get_short_id()
                stored_paper_id = _stored_paper_id_for_result(arxiv_paper_id, paper_ids)
                paper = {
                    "title": result.title,
                    "authors": [author.name for author in result.authors],
                    "url": f"https://arxiv.org/abs/{arxiv_paper_id}",
                    **_local_paper_hints(stored_paper_id),
                }
                if include_abstracts:
                    paper["abstract"] = result.summary
                papers.append(paper)
            return papers

        async def _call() -> list[dict[str, Any]]:
            return await asyncio.to_thread(_list_with_client)

        papers = await _run_live_arxiv_call(_call)
        return _with_common_metadata({"status": "success", "total_papers": len(paper_ids), "papers": papers})
    except arxiv.ArxivError as exc:
        if _is_rate_limit_error(exc):
            return _rate_limited_response(operation="list_papers", exc=exc)
        return _with_common_metadata({"status": "error", "message": f"ArXiv API error - {exc}"})
    except Exception as exc:
        if _is_rate_limit_error(exc):
            return _rate_limited_response(operation="list_papers", exc=exc)
        return _with_common_metadata({"status": "error", "message": f"Error: {exc}"})


def _extract_markdown_section(content: str, section: str) -> tuple[str, dict[str, Any]]:
    wanted = section.strip().lower()
    lines = content.splitlines()
    start = None
    start_level = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        title = stripped.lstrip("#").strip().lower()
        if wanted in title:
            start = index
            start_level = len(stripped) - len(stripped.lstrip("#"))
            break
    if start is None:
        return "", {"selected": section, "found": False}
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if not stripped.startswith("#"):
            continue
        level = len(stripped) - len(stripped.lstrip("#"))
        if level <= start_level:
            end = index
            break
    return "\n".join(lines[start:end]).strip(), {"selected": section, "found": True, "start_line": start + 1, "end_line": end}


def _paginate_content(content: str, *, offset: int = 0, max_chars: int | None = None) -> tuple[str, dict[str, Any]]:
    total_chars = len(content)
    normalized_offset = max(0, min(int(offset or 0), total_chars))
    normalized_max = int(max_chars) if max_chars is not None else total_chars
    normalized_max = max(1, normalized_max)
    end = min(total_chars, normalized_offset + normalized_max)
    return content[normalized_offset:end], {
        "offset": normalized_offset,
        "max_chars": normalized_max,
        "returned_chars": end - normalized_offset,
        "total_chars": total_chars,
        "truncated": end < total_chars,
        "next_offset": end if end < total_chars else None,
    }


async def read_paper(*, paper_id: str, max_chars: int | None = None, offset: int = 0, section: str | None = None) -> dict[str, Any]:
    try:
        paper_path = _get_paper_path(paper_id, ".md")
        if not paper_path.exists():
            return _with_common_metadata({
                "status": "error",
                "message": f"Paper {paper_id} not found in storage. You may need to download it first using download_paper.",
                "next_action": f"call download_paper with paper_id={paper_id!r}, then poll download_paper with check_status=true until status is success",
                **_local_paper_hints(paper_id),
            })
        content = paper_path.read_text(encoding="utf-8")
        section_info = {"selected": section, "found": None}
        if section:
            content, section_info = _extract_markdown_section(content, section)
            if not content:
                return _with_common_metadata({
                    "status": "not_found",
                    "message": f"Section {section!r} was not found in paper {paper_id}.",
                    "section": section_info,
                    **_local_paper_hints(paper_id),
                })
        page_content, pagination = _paginate_content(content, offset=offset, max_chars=max_chars)
        return _with_common_metadata({
            "status": "success",
            "content": page_content,
            "pagination": pagination,
            "section": section_info,
            **_local_paper_hints(paper_id),
        })
    except Exception as exc:
        return _with_common_metadata({"status": "error", "message": f"Error reading paper: {exc}", **_local_paper_hints(paper_id)})


DEEP_PAPER_ANALYSIS_PROMPT = """
You are an AI research assistant tasked with analyzing academic papers from arXiv.

AVAILABLE TOOLS:
1. read_paper: retrieve full content of a downloaded paper
2. download_paper: download and convert a paper if not present
3. search_papers: find related papers
4. list_papers: inspect which papers are already downloaded

WORKFLOW:
- First list_papers, then download_paper if needed, then read_paper.
- If the paper is unavailable, use search_papers for related work and context.

ANALYSIS STRUCTURE:
1) Executive Summary
2) Research Context
3) Methodology Analysis
4) Results Analysis
5) Practical Implications
6) Theoretical Implications
7) Future Directions
8) Broader Impact

Keep the analysis technically rigorous, concise, and actionable.
"""


def build_deep_analysis_prompt(paper_id: str) -> str:
    return (
        f"Analyze paper {paper_id}.\n\n"
        "Present your analysis with:\n"
        "1. Executive Summary (3-5 sentences)\n"
        "2. Detailed Analysis\n"
        "3. Visual Breakdown (figures/tables)\n"
        "4. Related Work Map\n"
        "5. Implementation Notes\n\n"
        f"{DEEP_PAPER_ANALYSIS_PROMPT}"
    )
