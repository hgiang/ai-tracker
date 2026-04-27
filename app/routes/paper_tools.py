from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.item import ContentType, Item
from app.services.arxiv import fetch_abstract, fetch_pdf_bytes
from app.services.kimi import call_kimi
from app.services.notebook_builder import build_notebook

logger = logging.getLogger(__name__)

router = APIRouter(tags=["paper-tools"])

SUMMARY_SYSTEM = (
    "You are an expert ML research communicator. Summarise research papers "
    "clearly and concisely for practising ML engineers."
)

SUMMARY_USER_TEMPLATE = """\
Paper title: {title}

Abstract:
{abstract}

Write a 3-5 paragraph summary of this paper for an ML practitioner. Cover:
1. The problem being solved and why it matters
2. The core technical approach and key innovations
3. Main results and what they mean in practice
4. Limitations or open questions

Use clear, direct language. No bullet points — flowing paragraphs only.
"""


async def _get_paper_item(item_id: int, db: AsyncSession) -> Item:
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.content_type != ContentType.PAPER:
        raise HTTPException(status_code=404, detail="Item is not a paper")
    return item


@router.get("/items/{item_id}/summary")
async def get_paper_summary(
    item_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    item = await _get_paper_item(item_id, db)

    # Return cached summary if available
    meta: dict = json.loads(item.metadata_json) if item.metadata_json else {}
    if cached := meta.get("llm_summary"):
        return {"item_id": item_id, "title": item.title, "summary": cached}

    # Fetch abstract from arXiv, fall back to stored summary
    abstract = await fetch_abstract(item.url) or item.summary or ""
    if not abstract:
        raise HTTPException(status_code=422, detail="Could not retrieve paper abstract")

    try:
        summary = await call_kimi(
            system=SUMMARY_SYSTEM,
            user=SUMMARY_USER_TEMPLATE.format(title=item.title, abstract=abstract),
            max_tokens=2048,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Kimi API error for item %s", item_id)
        raise HTTPException(status_code=502, detail="LLM API error") from exc

    # Cache in metadata_json
    meta["llm_summary"] = summary
    item.metadata_json = json.dumps(meta)
    await db.commit()

    return {"item_id": item_id, "title": item.title, "summary": summary}


@router.post("/items/{item_id}/notebook")
async def generate_notebook(
    item_id: int, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    item = await _get_paper_item(item_id, db)

    async def event_stream():
        try:
            yield _sse({"status": "fetching_pdf"})
            pdf_bytes = await fetch_pdf_bytes(item.url)

            async for event in build_notebook(pdf_bytes):
                yield _sse(event)
        except Exception as exc:
            logger.exception("Notebook generation failed for item %s", item_id)
            yield _sse({"status": "error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
