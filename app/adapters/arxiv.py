import xml.etree.ElementTree as ET

from app.adapters.base import BaseAdapter, parse_iso_utc
from app.models.item import ContentType
from app.schemas.item import NormalizedItem

ARXIV_API = "https://export.arxiv.org/api/query"
FETCH_LIMIT = 30
NS = {"atom": "http://www.w3.org/2005/Atom"}


class ArxivAdapter(BaseAdapter):
    async def fetch(self, checkpoint: str | None = None) -> tuple[list[NormalizedItem], str | None]:
        category = self.config.get("category", "cs.AI")
        query = f"cat:{category}"
        url = f"{ARXIV_API}?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results={FETCH_LIMIT}"

        xml_text = await self._get_text(url)
        root = ET.fromstring(xml_text)
        entries = root.findall("atom:entry", NS)

        new_checkpoint = None
        items: list[NormalizedItem] = []
        for entry in entries:
            entry_id = entry.findtext("atom:id", "", NS)
            arxiv_id = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else entry_id

            if checkpoint and arxiv_id <= checkpoint:
                continue
            if new_checkpoint is None:
                new_checkpoint = arxiv_id

            title = entry.findtext("atom:title", "", NS).strip().replace("\n", " ")
            summary = entry.findtext("atom:summary", "", NS).strip()
            authors = [a.findtext("atom:name", "", NS) for a in entry.findall("atom:author", NS)]
            published = entry.findtext("atom:published", "", NS)

            pub_dt = parse_iso_utc(published) if published else None

            pdf_link = entry_id.replace("/abs/", "/pdf/")

            items.append(
                NormalizedItem(
                    source_item_id=arxiv_id,
                    url=pdf_link,
                    title=title,
                    summary=summary[:500],
                    content_type=ContentType.PAPER,
                    author=", ".join(authors[:3]),
                    published_at=pub_dt,
                )
            )
        return items, new_checkpoint or checkpoint
