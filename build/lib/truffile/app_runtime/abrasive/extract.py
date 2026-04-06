import trafilatura
from trafilatura.metadata import Document
from trafilatura.xml import xmltotxt
from .fetch import fetch_html
from typing import Tuple, NamedTuple
from dataclasses import dataclass, field
import json 
from datetime import datetime
import logging

def _extract_html(html: str, url : str | None = None) -> str | None:
    text = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        favor_recall=False,
        deduplicate=True,
        favor_precision=True,
        include_comments=True,
        include_links=True,
        include_tables=False,
        with_metadata=False
    )
    return text.strip() if text else None

def _extract_html_metadata(html: str, url : str | None = None) -> dict | None:
    # this actually still includes raw text + so much extra stuff!! not just meta 
    # todo: look into this more! super cool! 
    meta = trafilatura.extract(
        html,
        url=url,
        output_format="json",
        favor_recall=False,
        deduplicate=True,
        favor_precision=True,
        include_links=True,
        include_tables=False,
        with_metadata=True,
        only_with_metadata=True  # we probably dont want this... 

    )
    if not meta:
        return None
    return json.loads(meta)

def extract_text_from_url(url: str) -> str | None:
    html = fetch_html(url)
    if html is None:
        return None
    return _extract_html(html, url=url)

def extract_text_and_metadata_from_url(url: str) -> Tuple[str | None, dict | None]:
    html = fetch_html(url)
    if html is None:
        return None, None
    metadata = _extract_html_metadata(html, url=url)
    if metadata is None:
        return _extract_html(html, url=url), None
    text = None
    if hasattr(metadata, 'raw_text'):
        text = metadata['raw_text']
        metadata.pop('raw_text')
    return text, metadata

def extract_metadata_from_url(url: str) -> dict | None:
    html = fetch_html(url)
    if html is None:
        return None
    return _extract_html_metadata(html, url=url)

@dataclass
class ExtractedContent():
    source_url: str 
    title : str | None
    description : str | None
    text: str | None
    date : datetime | None
    source_name : str | None = None
    images: list[str] = field(default_factory=list)
    comments : list[str] = field(default_factory=list)
    doc : Document | None = None

def _extract_content_from_html(html: str, url : str | None  ) -> ExtractedContent | None:
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    extracted = trafilatura.bare_extraction(
        filecontent=html,
        url=url,
        favor_recall=False,
        output_format="markdown",
        deduplicate=True,
        favor_precision=True,
        include_comments=True,
        include_tables=True,
        include_links=True, #experimental
        include_images=True, #experimental
        with_metadata=True,
        date_extraction_params={
            "original_date": True,
            "max_date" : datetime.now().strftime(DATE_FORMAT),
            "extensive_search": True,
            "outputformat": DATE_FORMAT
        }
    )
    if not extracted or not isinstance(extracted, Document):
        return None
    doc : Document = extracted

    if doc.body is not None:
        text = xmltotxt(doc.body, include_formatting=True)
    else:
        text = doc.text if doc.text else (doc.raw_text if doc.raw_text else None)
    comments_text = doc.comments
    if doc.commentsbody is not None:
        comments_text = xmltotxt(doc.commentsbody, include_formatting=True)
    timestamp = None
    if doc.date:
        try:
            timestamp = datetime.strptime(doc.date, DATE_FORMAT)
        except Exception:
            timestamp = None
        if not timestamp:
            try:
                timestamp = datetime.strptime(doc.date, "%Y-%m-%d")
            except Exception:
                timestamp = None
        

    return ExtractedContent(
        source_url = doc.url if doc.url else (url if url else ""),
        title = doc.title,
        description = doc.description,
        text = text,
        date= timestamp,
        source_name=doc.sitename,
        images=[doc.image ] if doc.image else [],
        comments= [comments_text ] if comments_text else [],
        doc = doc
    )
    
def extract_content_from_url(url : str ) -> ExtractedContent | None:
    html = fetch_html(url)
    if html is None:
        return None
    return _extract_content_from_html(html, url=url)
    

if __name__ == "__main__":
    url =  "https://www.theverge.com/news/836212/openai-code-red-chatgpt"
    content = extract_content_from_url(url)
    

    if content:
        print("Title:", content.title)
        print("timestamp:", content.date)
        print("Text snippet:", content.text[:256] if content.text else "No text")
        print("Images:", content.images)
        print("Comments:", content.comments)