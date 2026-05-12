from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.item import ContentType, Item
from app.services.arxiv import fetch_abstract, fetch_pdf_bytes
from app.services.llm_client import Provider, call_llm
from app.services.notebook_builder import build_notebook
from app.services.paper_reviewer import build_review

logger = logging.getLogger(__name__)

router = APIRouter(tags=["paper-tools"])

SUMMARY_SYSTEM = (
    "You are an expert ML research communicator. You produce structured paper "
    "summaries for practising ML engineers, following the academic paper "
    "summary template precisely. Every claim must be grounded in the abstract; "
    "if information is not available, write 'Not specified in abstract.'"
)

SUMMARY_USER_TEMPLATE = """\
Paper title: {title}

Abstract:
{abstract}

Produce a structured Markdown summary using this EXACT template. Keep it crisp — \
prefer bullets and short sentences over flowing prose.

## TL;DR
[2-3 sentence elevator pitch: what the paper does and why it matters for ML practitioners.]

## Problem & Motivation
[What gap or problem does this paper address? Why is it important? 2-3 sentences.]

## Approach
[The core technical method and key innovations. Be specific about architecture, \
algorithms, or techniques. 3-5 sentences.]

## Key Findings
- [Primary result with effect size, metric, or comparison where reported]
- [Second result]
- [Third result if applicable]

## Significance for Practitioners
[Why an ML engineer should care: when to apply this approach, what it unlocks, \
trade-offs to keep in mind. 2-3 sentences.]

## Limitations & Open Questions
- [Limitation or open question 1]
- [Limitation or open question 2]

Output only the Markdown summary — no preamble, no trailing text.
"""


class LLMRequest(BaseModel):
    provider: Provider
    api_key: str


async def _get_paper_item(item_id: int, db: AsyncSession) -> Item:
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.content_type != ContentType.PAPER:
        raise HTTPException(status_code=404, detail="Item is not a paper")
    return item


@router.post("/items/{item_id}/summary")
async def get_paper_summary(
    item_id: int,
    req: LLMRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = await _get_paper_item(item_id, db)

    # Return cached summary if available
    meta: dict = json.loads(item.metadata_json) if item.metadata_json else {}
    if cached := meta.get("llm_summary"):
        return {"item_id": item_id, "title": item.title, "summary": cached}

    abstract = await fetch_abstract(item.url) or item.summary or ""
    if not abstract:
        raise HTTPException(status_code=422, detail="Could not retrieve paper abstract")

    try:
        summary = await call_llm(
            provider=req.provider,
            api_key=req.api_key,
            system=SUMMARY_SYSTEM,
            user=SUMMARY_USER_TEMPLATE.format(title=item.title, abstract=abstract),
            max_tokens=2048,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("LLM API error for item %s", item_id)
        raise HTTPException(status_code=502, detail="LLM API error") from exc

    meta["llm_summary"] = summary
    item.metadata_json = json.dumps(meta)
    await db.commit()

    return {"item_id": item_id, "title": item.title, "summary": summary}


@router.post("/items/{item_id}/notebook")
async def generate_notebook(
    item_id: int,
    req: LLMRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    item = await _get_paper_item(item_id, db)
    provider = req.provider
    api_key = req.api_key

    async def event_stream():
        try:
            yield _sse({"status": "fetching_pdf"})
            pdf_bytes = await fetch_pdf_bytes(item.url)

            async def call_llm_fn(system: str, user: str, max_tokens: int) -> str:
                return await call_llm(
                    provider=provider,
                    api_key=api_key,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                )

            async for event in build_notebook(pdf_bytes, call_llm_fn):
                yield _sse(event)
        except Exception as exc:
            logger.exception("Notebook generation failed for item %s", item_id)
            yield _sse({"status": "error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/items/{item_id}/review")
async def generate_review(
    item_id: int,
    req: LLMRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    item = await _get_paper_item(item_id, db)
    provider = req.provider
    api_key = req.api_key

    async def event_stream():
        try:
            yield _sse({"status": "fetching_pdf"})
            pdf_bytes = await fetch_pdf_bytes(item.url)

            async def call_llm_fn(system: str, user: str, max_tokens: int) -> str:
                return await call_llm(
                    provider=provider,
                    api_key=api_key,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                )

            async for event in build_review(pdf_bytes, call_llm_fn):
                yield _sse(event)
        except Exception as exc:
            logger.exception("Review generation failed for item %s", item_id)
            yield _sse({"status": "error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
