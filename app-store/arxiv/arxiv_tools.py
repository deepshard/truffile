from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as et
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import arxiv
import httpx
from dateutil import parser as date_parser
from pypdf import PdfReader

from arxiv_common import MAX_RESULTS, get_storage_path

logger = logging.getLogger("arxiv.tools")
logger.setLevel(logging.INFO)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
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


def _safe_paper_filename(paper_id: str) -> str:
    return paper_id.replace("/", _SLASH_TOKEN)


def _get_paper_path(paper_id: str, suffix: str = ".md") -> Path:
    storage = get_storage_path()
    storage.mkdir(parents=True, exist_ok=True)
    return storage / f"{_safe_paper_filename(paper_id)}{suffix}"


def list_stored_paper_ids() -> list[str]:
    storage = get_storage_path()
    ids: list[str] = []
    for path in storage.glob("*.md"):
        ids.append(path.stem.replace(_SLASH_TOKEN, "/"))
    return ids


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


def _parse_arxiv_atom_response(xml_text: str) -> list[dict[str, Any]]:
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

        pdf_url: str | None = None
        for link in entry.findall("atom:link", ARXIV_NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")
                break
        if not pdf_url:
            pdf_url = f"https://arxiv.org/pdf/{paper_id}"

        results.append(
            {
                "id": short_id,
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "categories": categories,
                "published": published,
                "url": pdf_url,
                "resource_uri": f"arxiv://{short_id}",
            }
        )

    return results


async def _raw_arxiv_search(
    *,
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
    date_from: str | None = None,
    date_to: str | None = None,
    categories: list[str] | None = None,
) -> list[dict[str, Any]]:
    query_parts: list[str] = []

    if query.strip():
        query_parts.append(f"({query})")

    if categories:
        category_filter = " OR ".join(f"cat:{cat}" for cat in categories)
        query_parts.append(f"({category_filter})")

    if date_from or date_to:
        try:
            start_date = date_parser.parse(date_from).strftime("%Y%m%d0000") if date_from else "199107010000"
            end_date = date_parser.parse(date_to).strftime("%Y%m%d2359") if date_to else datetime.now().strftime("%Y%m%d2359")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid date format. Use YYYY-MM-DD format: {exc}") from exc
        query_parts.append(f"submittedDate:[{start_date}+TO+{end_date}]")

    if not query_parts:
        raise ValueError("No search criteria provided")

    final_query = " AND ".join(query_parts)
    sort_map = {"relevance": "relevance", "date": "submittedDate"}
    encoded_query = final_query.replace(" AND ", "+AND+").replace(" OR ", "+OR+").replace(" ", "+")
    url = (
        f"{ARXIV_API_URL}?search_query={encoded_query}"
        f"&max_results={max_results}"
        f"&sortBy={sort_map.get(sort_by, 'relevance')}"
        "&sortOrder=descending"
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
    return _parse_arxiv_atom_response(response.text)


def _process_paper(paper: arxiv.Result) -> dict[str, Any]:
    return {
        "id": paper.get_short_id(),
        "title": paper.title,
        "authors": [author.name for author in paper.authors],
        "abstract": paper.summary,
        "categories": paper.categories,
        "published": paper.published.isoformat(),
        "url": paper.pdf_url,
        "resource_uri": f"arxiv://{paper.get_short_id()}",
    }


async def search_papers(
    *,
    query: str,
    max_results: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
    categories: list[str] | None = None,
    sort_by: str = "relevance",
) -> dict[str, Any]:
    try:
        bounded_max = min(int(max_results), MAX_RESULTS)
        if categories and not _validate_categories(categories):
            return {"status": "error", "message": "Invalid category provided. Please check arXiv category names."}

        if date_from or date_to:
            results = await _raw_arxiv_search(
                query=_optimize_query(query) if query.strip() else "",
                max_results=bounded_max,
                sort_by=sort_by,
                date_from=date_from,
                date_to=date_to,
                categories=categories,
            )
            return {"status": "success", "total_results": len(results), "papers": results}

        client = arxiv.Client()
        query_parts: list[str] = []
        if query.strip():
            query_parts.append(f"({_optimize_query(query)})")
        if categories:
            query_parts.append("(" + " OR ".join(f"cat:{cat}" for cat in categories) + ")")
        if not query_parts:
            return {"status": "error", "message": "No search criteria provided"}

        final_query = " ".join(query_parts)
        sort_criterion = arxiv.SortCriterion.SubmittedDate if sort_by == "date" else arxiv.SortCriterion.Relevance
        search = arxiv.Search(query=final_query, max_results=bounded_max, sort_by=sort_criterion)

        papers: list[dict[str, Any]] = []
        for paper in client.results(search):
            if len(papers) >= bounded_max:
                break
            papers.append(_process_paper(paper))
        return {"status": "success", "total_results": len(papers), "papers": papers}
    except arxiv.ArxivError as exc:
        return {"status": "error", "message": f"ArXiv API error - {exc}"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


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
                    return {
                        "status": "success",
                        "message": "Paper is ready",
                        "resource_uri": f"file://{_get_paper_path(paper_id, '.md')}",
                    }
                return {"status": "unknown", "message": "No download or conversion in progress"}
            return {
                "status": status.status,
                "started_at": status.started_at.isoformat(),
                "completed_at": status.completed_at.isoformat() if status.completed_at else None,
                "error": status.error,
                "message": f"Paper conversion {status.status}",
            }

        if _get_paper_path(paper_id, ".md").exists():
            return {
                "status": "success",
                "message": "Paper already available",
                "resource_uri": f"file://{_get_paper_path(paper_id, '.md')}",
            }

        if paper_id in _conversion_statuses:
            status = _conversion_statuses[paper_id]
            return {
                "status": status.status,
                "message": f"Paper conversion {status.status}",
                "started_at": status.started_at.isoformat(),
            }

        pdf_path = _get_paper_path(paper_id, ".pdf")
        client = arxiv.Client()
        _conversion_statuses[paper_id] = ConversionStatus(
            paper_id=paper_id,
            status="downloading",
            started_at=datetime.now(),
        )

        paper = next(client.results(arxiv.Search(id_list=[paper_id])))
        paper.download_pdf(dirpath=pdf_path.parent, filename=pdf_path.name)

        status = _conversion_statuses[paper_id]
        status.status = "converting"
        asyncio.create_task(asyncio.to_thread(_convert_pdf_to_markdown, paper_id, pdf_path))
        return {
            "status": "converting",
            "message": "Paper downloaded, conversion started",
            "started_at": status.started_at.isoformat(),
        }
    except StopIteration:
        return {"status": "error", "message": f"Paper {paper_id} not found on arXiv"}
    except Exception as exc:
        return {"status": "error", "message": f"Error: {exc}"}


async def list_papers() -> dict[str, Any]:
    try:
        paper_ids = list_stored_paper_ids()
        if not paper_ids:
            return {"status": "success", "total_papers": 0, "papers": []}

        client = arxiv.Client()
        results = client.results(arxiv.Search(id_list=paper_ids))
        papers: list[dict[str, Any]] = []
        for result in results:
            papers.append(
                {
                    "id": result.get_short_id(),
                    "title": result.title,
                    "summary": result.summary,
                    "authors": [author.name for author in result.authors],
                    "links": [link.href for link in result.links],
                    "pdf_url": result.pdf_url,
                }
            )
        return {"status": "success", "total_papers": len(paper_ids), "papers": papers}
    except Exception as exc:
        return {"status": "error", "message": f"Error: {exc}"}


async def read_paper(*, paper_id: str) -> dict[str, Any]:
    try:
        paper_path = _get_paper_path(paper_id, ".md")
        if not paper_path.exists():
            return {
                "status": "error",
                "message": f"Paper {paper_id} not found in storage. You may need to download it first using download_paper.",
            }
        content = paper_path.read_text(encoding="utf-8")
        return {"status": "success", "paper_id": paper_id, "content": content}
    except Exception as exc:
        return {"status": "error", "message": f"Error reading paper: {exc}"}


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
