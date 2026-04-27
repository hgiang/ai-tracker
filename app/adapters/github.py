import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app.adapters.base import BaseAdapter
from app.models.item import ContentType
from app.schemas.item import NormalizedItem

logger = logging.getLogger(__name__)

TRENDING_URL = "https://github.com/trending"
TIME_RANGES = ("daily", "weekly")


class GitHubAdapter(BaseAdapter):
    """Scrapes github.com/trending for daily + weekly trending repos."""

    async def fetch(self, checkpoint: str | None = None) -> tuple[list[NormalizedItem], str | None]:
        language = self.config.get("language", "")  # empty = all languages
        url = f"{TRENDING_URL}/{language}" if language else TRENDING_URL

        now = datetime.now(timezone.utc)
        seen: set[str] = set()
        items: list[NormalizedItem] = []

        for since in TIME_RANGES:
            html = await self._get_text(url, params={"since": since})
            repos = _parse_trending(html)
            logger.info("GitHub trending %s: %s repos parsed", since, len(repos))

            for repo in repos:
                if repo["full_name"] in seen:
                    continue
                seen.add(repo["full_name"])
                items.append(
                    NormalizedItem(
                        source_item_id=repo["full_name"],
                        url=repo["url"],
                        title=f"{repo['full_name']}: {repo['description']}".strip(": "),
                        summary=repo["description"] or None,
                        content_type=ContentType.REPO,
                        author=repo["full_name"].split("/")[0],
                        published_at=now,
                        points=repo["stars"],
                        comment_count=repo["stars_today"],
                    )
                )

        return items, now.isoformat()


def _parse_trending(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    for article in soup.select("article.Box-row"):
        link = article.select_one("h2 a")
        if not link or not link.get("href"):
            continue
        full_name = link["href"].lstrip("/").strip()
        if "/" not in full_name:
            continue

        desc_el = article.select_one("p")
        description = desc_el.get_text(strip=True) if desc_el else ""

        star_el = article.select_one(f'a[href="/{full_name}/stargazers"]')
        stars = _parse_count(star_el.get_text(strip=True) if star_el else "")

        today_el = article.select_one("span.d-inline-block.float-sm-right")
        stars_today = 0
        if today_el:
            m = re.search(r"([\d,]+)", today_el.get_text(strip=True))
            if m:
                stars_today = _parse_count(m.group(1))

        results.append(
            {
                "full_name": full_name,
                "url": f"https://github.com/{full_name}",
                "description": description,
                "stars": stars,
                "stars_today": stars_today,
            }
        )
    return results


def _parse_count(text: str) -> int:
    text = text.replace(",", "").strip().lower()
    if not text:
        return 0
    try:
        if text.endswith("k"):
            return int(float(text[:-1]) * 1000)
        return int(text)
    except ValueError:
        return 0
