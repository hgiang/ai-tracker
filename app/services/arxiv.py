import logging
import re

import httpx
from bs4 import BeautifulSoup

_ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)")
logger = logging.getLogger(__name__)


def arxiv_id_from_url(url: str) -> str | None:
    """Extract the arXiv paper ID from an abs or pdf URL."""
    m = _ARXIV_ID_RE.search(url)
    return m.group(1) if m else None


def pdf_url_from_arxiv_url(url: str) -> str | None:
    """Convert an arXiv abs URL to the corresponding PDF URL."""
    arxiv_id = arxiv_id_from_url(url)
    if not arxiv_id:
        return None
    return f"https://arxiv.org/pdf/{arxiv_id}"


async def fetch_abstract(arxiv_url: str) -> str | None:
    """Fetch the abstract text from the arXiv abstract page.

    Returns None if the fetch fails or no abstract is found.
    """
    arxiv_id = arxiv_id_from_url(arxiv_url)
    if not arxiv_id:
        return None
    abs_url = f"https://export.arxiv.org/abs/{arxiv_id}"
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(abs_url, headers={"User-Agent": "ai-tracker/0.1"})
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("fetch_abstract failed for %s: %s", arxiv_url, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    tag = soup.find("blockquote", class_="abstract")
    if not tag:
        return None
    # Remove the "Abstract:" label span if present
    for span in tag.find_all("span", class_="descriptor"):
        span.decompose()
    return tag.get_text(strip=True)


async def fetch_pdf_bytes(arxiv_url: str) -> bytes:
    """Download the PDF for an arXiv paper. Raises httpx.HTTPError on failure."""
    pdf_url = pdf_url_from_arxiv_url(arxiv_url)
    if not pdf_url:
        raise ValueError(f"Cannot derive PDF URL from: {arxiv_url}")
    async with httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True,
        headers={"User-Agent": "ai-tracker/0.1"},
    ) as client:
        resp = await client.get(pdf_url)
        resp.raise_for_status()
        return resp.content
