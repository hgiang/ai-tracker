# Paper Tools (Summary + Notebook) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Summary and Notebook buttons to paper item cards; each opens a new tab backed by a FastAPI endpoint that calls Kimi K2.5.

**Architecture:** New `app/routes/paper_tools.py` exposes `GET /api/items/{id}/summary` (JSON) and `POST /api/items/{id}/notebook` (SSE stream). Two static HTML pages consume them. The item card in `components.js` conditionally renders the buttons for `content_type === "paper"`.

**Tech Stack:** FastAPI, openai SDK (OpenAI-compatible, pointed at Kimi), pymupdf for PDF text, nbformat for notebook assembly, vanilla JS + SSE EventSource.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/config.py` | Modify | Add `kimi_api_key`, `kimi_base_url`, `kimi_model` |
| `.env` / `.env.example` | Modify | Add `KIMI_API_KEY` placeholder |
| `pyproject.toml` | Modify | Add `openai`, `nbformat`, `pymupdf` deps |
| `app/services/kimi.py` | Create | Thin async wrapper around OpenAI-compatible Kimi API |
| `app/services/arxiv.py` | Create | Fetch arXiv abstract HTML and PDF bytes |
| `app/services/notebook_builder.py` | Create | 3-stage Kimi pipeline + nbformat assembly |
| `app/routes/paper_tools.py` | Create | `/summary` and `/notebook` endpoints |
| `app/main.py` | Modify | Register router; add `/summary` and `/notebook` page routes |
| `static/summary.html` | Create | Summary page |
| `static/notebook.html` | Create | Notebook page with SSE progress |
| `static/js/components.js` | Modify | Add paper action buttons to `renderItemCard` |
| `static/css/style.css` | Modify | Styles for `.paper-actions`, `.btn-summary`, `.btn-notebook` |

---

## Task 1: Config, deps, and env

**Files:**
- Modify: `app/config.py`
- Modify: `pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Add Kimi config fields to `app/config.py`**

Replace the existing `Settings` class body:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./ai_tracker.db"

    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    github_token: str = ""
    x_bearer_token: str = ""

    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    kimi_model: str = "kimi-k2.5"

    retention_days: int = 180

    relevance_keywords: str = (
        "llm,large language model,gpt,claude,gemini,deep learning,"
        "transformer,agentic,ai agent,rag,fine-tuning,diffusion,multimodal"
    )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def keywords_list(self) -> list[str]:
        return [k.strip().lower() for k in self.relevance_keywords.split(",") if k.strip()]


settings = Settings()
```

- [ ] **Step 2: Add deps to `pyproject.toml`**

In the `dependencies` list, add after `"python-dotenv>=1.0.0",`:

```toml
    "openai>=1.0.0",
    "nbformat>=5.10.0",
    "pymupdf>=1.24.0",
```

- [ ] **Step 3: Add `.env.example` entries**

Append to `.env.example`:

```
# Kimi K2.5 LLM API (for paper summary and notebook generation)
KIMI_API_KEY=your_kimi_api_key_here
KIMI_BASE_URL=https://api.moonshot.ai/v1
KIMI_MODEL=kimi-k2.5
```

- [ ] **Step 4: Install new deps**

```bash
.venv/bin/pip install "openai>=1.0.0" "nbformat>=5.10.0" "pymupdf>=1.24.0"
```

Expected: packages install without error.

- [ ] **Step 5: Commit**

```bash
git add app/config.py pyproject.toml .env.example
git commit -m "feat: add Kimi K2.5 config fields and deps"
```

---

## Task 2: Kimi client service

**Files:**
- Create: `app/services/kimi.py`
- Create: `tests/test_kimi_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_kimi_service.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.kimi import call_kimi


@pytest.mark.unit
@patch("app.services.kimi.settings")
async def test_call_kimi_returns_content(mock_settings):
    mock_settings.kimi_api_key = "test-key"
    mock_settings.kimi_base_url = "https://api.moonshot.ai/v1"
    mock_settings.kimi_model = "kimi-k2.5"

    mock_message = MagicMock()
    mock_message.content = "Hello, world!"
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.kimi.AsyncOpenAI", return_value=mock_client):
        result = await call_kimi(system="You are helpful.", user="Say hi.")

    assert result == "Hello, world!"


@pytest.mark.unit
@patch("app.services.kimi.settings")
async def test_call_kimi_raises_on_empty_key(mock_settings):
    mock_settings.kimi_api_key = ""

    with pytest.raises(ValueError, match="KIMI_API_KEY"):
        await call_kimi(system="sys", user="msg")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_kimi_service.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `app.services.kimi` doesn't exist yet.

- [ ] **Step 3: Create `app/services/kimi.py`**

```python
from openai import AsyncOpenAI

from app.config import settings


async def call_kimi(system: str, user: str, max_tokens: int = 8192) -> str:
    """Call Kimi K2.5 via the OpenAI-compatible API and return the response text."""
    if not settings.kimi_api_key:
        raise ValueError("KIMI_API_KEY is not configured")

    async with AsyncOpenAI(
        api_key=settings.kimi_api_key,
        base_url=settings.kimi_base_url,
    ) as client:
        response = await client.chat.completions.create(
            model=settings.kimi_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )
    return response.choices[0].message.content
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_kimi_service.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/kimi.py tests/test_kimi_service.py
git commit -m "feat: add Kimi K2.5 async client service"
```

---

## Task 3: arXiv fetch service

**Files:**
- Create: `app/services/arxiv.py`
- Create: `tests/test_arxiv_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_arxiv_service.py`:

```python
import pytest

from app.services.arxiv import arxiv_id_from_url, pdf_url_from_arxiv_url


@pytest.mark.unit
def test_arxiv_id_from_abs_url():
    assert arxiv_id_from_url("https://arxiv.org/abs/2501.12345") == "2501.12345"


@pytest.mark.unit
def test_arxiv_id_from_abs_url_with_version():
    assert arxiv_id_from_url("https://arxiv.org/abs/2501.12345v2") == "2501.12345v2"


@pytest.mark.unit
def test_arxiv_id_from_pdf_url():
    assert arxiv_id_from_url("https://arxiv.org/pdf/2501.12345") == "2501.12345"


@pytest.mark.unit
def test_arxiv_id_from_unknown_url_returns_none():
    assert arxiv_id_from_url("https://example.com/paper") is None


@pytest.mark.unit
def test_pdf_url_from_arxiv_url():
    assert pdf_url_from_arxiv_url("https://arxiv.org/abs/2501.12345") == "https://arxiv.org/pdf/2501.12345"


@pytest.mark.unit
def test_pdf_url_from_non_arxiv_returns_none():
    assert pdf_url_from_arxiv_url("https://example.com/paper") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_arxiv_service.py -v
```

Expected: `ImportError` — module doesn't exist.

- [ ] **Step 3: Create `app/services/arxiv.py`**

```python
import re

import httpx

_ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)")


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
    except Exception:
        return None

    from bs4 import BeautifulSoup
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_arxiv_service.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/arxiv.py tests/test_arxiv_service.py
git commit -m "feat: add arXiv abstract and PDF fetch service"
```

---

## Task 4: Notebook builder service

**Files:**
- Create: `app/services/notebook_builder.py`

- [ ] **Step 1: Create `app/services/notebook_builder.py`**

```python
"""Three-stage Kimi pipeline to convert a research paper PDF into a Jupyter notebook.

Stage 1 — Analyse: extract structured paper metadata from raw text.
Stage 2 — Design: plan the toy implementation structure.
Stage 3 — Generate: produce cell-by-cell notebook content.
"""
from __future__ import annotations

import base64
import json
from typing import AsyncIterator

import fitz  # pymupdf
import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from app.services.kimi import call_kimi

SYSTEM_PROMPT = (
    "You are an expert research engineer and educator who faithfully implements "
    "academic papers as runnable, educational Python code. You use real ML components "
    "(PyTorch, Transformer layers, actual training loops) at a reduced scale that "
    "runs on CPU. You prioritize faithful replication of the paper's architecture "
    "and algorithms while making the code deeply educational with clear explanations "
    "and insightful visualizations."
)

ANALYSIS_PROMPT = """\
Read this research paper text and extract a structured analysis.

Return a JSON object with exactly these fields:
{
  "title": "Full paper title",
  "authors": "Author list as a single string",
  "abstract_summary": "2-3 sentence plain English summary",
  "problem_statement": "What problem does the paper solve? (2-3 sentences)",
  "key_insight": "The core idea or innovation in one sentence",
  "key_contributions": ["Contribution 1", "Contribution 2", "Contribution 3"],
  "algorithms": [
    {
      "name": "Algorithm name",
      "description": "What this algorithm does",
      "steps": ["Step 1", "Step 2"],
      "is_core": true
    }
  ],
  "model_architecture": {
    "type": "Transformer/CNN/RNN/etc.",
    "key_layers": ["list of layer types"],
    "dimensions": "hidden dim, num heads, etc."
  },
  "research_field": "Primary research field in 2-4 words"
}

Paper text:
{paper_text}
"""

DESIGN_PROMPT = """\
Given the paper analysis below, design a toy Jupyter notebook implementation plan.

Return a JSON object with:
{
  "notebook_title": "Clear descriptive title",
  "sections": [
    {
      "title": "Section title (e.g. Setup & Imports)",
      "description": "What this section does",
      "cell_type": "code or markdown",
      "content_hint": "Brief hint about what code/text goes here"
    }
  ],
  "model_config": {
    "embed_dim": 64,
    "num_layers": 2,
    "num_heads": 4,
    "vocab_size": 1000,
    "max_seq_len": 32
  },
  "training_config": {
    "num_epochs": 5,
    "batch_size": 16,
    "learning_rate": 0.001
  }
}

Paper analysis:
{analysis_json}
"""

GENERATE_PROMPT = """\
Given the paper analysis and notebook design below, generate the complete Jupyter notebook.

Return a JSON object with:
{
  "cells": [
    {
      "cell_type": "markdown",
      "source": "# Title\\n\\nMarkdown content here"
    },
    {
      "cell_type": "code",
      "source": "import torch\\n# Python code here"
    }
  ]
}

Include:
- A markdown header cell with title, paper reference, and brief description
- All necessary imports in the first code cell
- Educational comments throughout
- A training loop with loss logging
- A brief results/visualization section

Paper analysis:
{analysis_json}

Notebook design:
{design_json}
"""


def _extract_text(pdf_bytes: bytes, max_chars: int = 40_000) -> str:
    """Extract text from PDF bytes using pymupdf, capped at max_chars."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    parts: list[str] = []
    total = 0
    for page in doc:
        text = page.get_text()
        parts.append(text)
        total += len(text)
        if total >= max_chars:
            break
    doc.close()
    return "".join(parts)[:max_chars]


def _parse_json_response(text: str) -> dict:
    """Extract the first JSON object from an LLM response string."""
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON object found in response: {text[:200]}")
    return json.loads(text[start:end])


def _assemble_notebook(cells_data: list[dict]) -> str:
    """Build a .ipynb JSON string from a list of cell dicts."""
    nb = new_notebook()
    nb.cells = []
    for cell in cells_data:
        source = cell.get("source", "")
        if cell.get("cell_type") == "markdown":
            nb.cells.append(new_markdown_cell(source))
        else:
            nb.cells.append(new_code_cell(source))
    nbformat.validate(nb)
    return nbformat.writes(nb)


async def build_notebook(pdf_bytes: bytes) -> AsyncIterator[dict]:
    """Three-stage pipeline. Yields status dicts; final yield contains notebook_b64."""
    yield {"status": "analysing"}
    paper_text = _extract_text(pdf_bytes)
    analysis_raw = await call_kimi(
        system=SYSTEM_PROMPT,
        user=ANALYSIS_PROMPT.format(paper_text=paper_text),
        max_tokens=8192,
    )
    analysis = _parse_json_response(analysis_raw)

    yield {"status": "designing"}
    design_raw = await call_kimi(
        system=SYSTEM_PROMPT,
        user=DESIGN_PROMPT.format(analysis_json=json.dumps(analysis, indent=2)),
        max_tokens=8192,
    )
    design = _parse_json_response(design_raw)

    yield {"status": "generating"}
    cells_raw = await call_kimi(
        system=SYSTEM_PROMPT,
        user=GENERATE_PROMPT.format(
            analysis_json=json.dumps(analysis, indent=2),
            design_json=json.dumps(design, indent=2),
        ),
        max_tokens=32768,
    )
    cells_data = _parse_json_response(cells_raw)
    notebook_json = _assemble_notebook(cells_data.get("cells", []))
    notebook_b64 = base64.b64encode(notebook_json.encode()).decode()

    title = analysis.get("title", "notebook")
    yield {"status": "done", "notebook_b64": notebook_b64, "title": title}
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
.venv/bin/python -c "from app.services.notebook_builder import build_notebook; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/notebook_builder.py
git commit -m "feat: add 3-stage notebook builder service"
```

---

## Task 5: Summary and Notebook API endpoints

**Files:**
- Create: `app/routes/paper_tools.py`
- Create: `tests/test_paper_tools.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_paper_tools.py`:

```python
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.item import ContentType, Item


@pytest.fixture
def paper_item():
    return Item(
        id=1,
        source_id=1,
        source_item_id="arxiv:2501.12345",
        url="https://arxiv.org/abs/2501.12345",
        canonical_url="https://arxiv.org/abs/2501.12345",
        title="Test Paper",
        normalized_title="test paper",
        content_type=ContentType.PAPER,
        relevance_score=0.8,
        metadata_json=None,
    )


@pytest.mark.integration
async def test_summary_returns_cached(paper_item):
    import json
    paper_item.metadata_json = json.dumps({"llm_summary": "cached summary text"})

    with patch("app.routes.paper_tools.get_db"):
        with patch("app.routes.paper_tools._get_paper_item", return_value=paper_item):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/items/1/summary")

    assert resp.status_code == 200
    assert resp.json()["summary"] == "cached summary text"


@pytest.mark.integration
async def test_summary_returns_404_for_non_paper():
    non_paper = Item(
        id=2,
        source_id=1,
        source_item_id="hn:123",
        url="https://news.ycombinator.com/item?id=123",
        canonical_url="https://news.ycombinator.com/item?id=123",
        title="HN Post",
        normalized_title="hn post",
        content_type=ContentType.NEWS,
        relevance_score=0.5,
        metadata_json=None,
    )
    with patch("app.routes.paper_tools._get_paper_item", return_value=non_paper):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/items/2/summary")

    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_paper_tools.py -v
```

Expected: `ImportError` or `AttributeError` — route doesn't exist.

- [ ] **Step 3: Create `app/routes/paper_tools.py`**

```python
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
```

- [ ] **Step 4: Register router in `app/main.py`**

Add after the existing imports line `from app.routes import digests, health, items, sources`:

```python
from app.routes import digests, health, items, paper_tools, sources
```

Add after `app.include_router(digests.router, prefix="/api")`:

```python
app.include_router(paper_tools.router, prefix="/api")
```

Also add two static page routes after the existing `/` route:

```python
@app.get("/summary")
async def serve_summary():
    return FileResponse(STATIC_DIR / "summary.html")


@app.get("/notebook")
async def serve_notebook():
    return FileResponse(STATIC_DIR / "notebook.html")
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/test_paper_tools.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/routes/paper_tools.py app/main.py tests/test_paper_tools.py
git commit -m "feat: add paper summary and notebook SSE endpoints"
```

---

## Task 6: Summary page (`static/summary.html`)

**Files:**
- Create: `static/summary.html`

- [ ] **Step 1: Create `static/summary.html`**

```html
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Paper Summary — AI Tracker</title>
  <link rel="stylesheet" href="/static/css/style.css" />
  <style>
    .summary-page { max-width: 720px; margin: 3rem auto; padding: 0 1.5rem; }
    .summary-page h1 { font-size: 1.5rem; margin-bottom: 1.5rem; line-height: 1.4; }
    .summary-body { line-height: 1.8; color: var(--text-secondary); }
    .summary-body p { margin-bottom: 1rem; }
    .back-link { display: inline-flex; align-items: center; gap: 0.3rem;
      color: var(--accent-text); font-size: 0.85rem; margin-bottom: 2rem;
      text-decoration: none; }
    .back-link:hover { text-decoration: underline; }
    .spinner-wrap { display: flex; align-items: center; gap: 0.75rem;
      color: var(--text-secondary); margin-top: 3rem; }
    .error-msg { color: var(--danger); margin-top: 2rem; }
    .source-badge { font-size: 0.75rem; color: var(--text-tertiary);
      margin-bottom: 0.5rem; }
  </style>
</head>
<body>
  <div class="summary-page">
    <a class="back-link" href="javascript:history.back()">← Back</a>
    <div id="content">
      <div class="spinner-wrap">
        <span class="spinner"></span>
        <span>Generating summary with Kimi K2.5…</span>
      </div>
    </div>
  </div>

  <script type="module">
    import { renderMarkdown } from '/static/js/components.js';

    const params = new URLSearchParams(location.search);
    const itemId = params.get('item_id');
    const content = document.getElementById('content');

    if (!itemId) {
      content.innerHTML = '<p class="error-msg">Missing item_id parameter.</p>';
    } else {
      fetch(`/api/items/${itemId}/summary`)
        .then(async (resp) => {
          if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
          }
          return resp.json();
        })
        .then(({ title, summary }) => {
          document.title = `${title} — AI Tracker`;
          content.innerHTML = `
            <div class="source-badge">AI-generated summary · Kimi K2.5</div>
            <h1>${escapeHtml(title)}</h1>
            <div class="summary-body">${renderMarkdown(summary)}</div>
          `;
        })
        .catch((err) => {
          content.innerHTML = `<p class="error-msg">Error: ${escapeHtml(err.message)}</p>`;
        });
    }

    function escapeHtml(str) {
      const el = document.createElement('div');
      el.textContent = str;
      return el.innerHTML;
    }

    // Apply saved theme
    const theme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', theme);
  </script>
</body>
</html>
```

- [ ] **Step 2: Verify the page loads**

Start the server if not running: `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`

Open: `http://127.0.0.1:8000/summary?item_id=1`

Expected: spinner renders; if no paper items in DB, it shows a "not found" error (that's correct behaviour at this stage).

- [ ] **Step 3: Commit**

```bash
git add static/summary.html
git commit -m "feat: add paper summary static page"
```

---

## Task 7: Notebook page (`static/notebook.html`)

**Files:**
- Create: `static/notebook.html`

- [ ] **Step 1: Create `static/notebook.html`**

```html
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Paper to Notebook — AI Tracker</title>
  <link rel="stylesheet" href="/static/css/style.css" />
  <style>
    .notebook-page { max-width: 640px; margin: 3rem auto; padding: 0 1.5rem; }
    .notebook-page h1 { font-size: 1.4rem; margin-bottom: 0.5rem; }
    .subtitle { color: var(--text-tertiary); font-size: 0.85rem; margin-bottom: 2rem; }
    .back-link { display: inline-flex; align-items: center; gap: 0.3rem;
      color: var(--accent-text); font-size: 0.85rem; margin-bottom: 2rem;
      text-decoration: none; }
    .back-link:hover { text-decoration: underline; }
    .progress-list { list-style: none; padding: 0; margin: 1.5rem 0; }
    .progress-list li { display: flex; align-items: center; gap: 0.75rem;
      padding: 0.6rem 0; color: var(--text-secondary); font-size: 0.95rem; }
    .step-icon { font-size: 1.1rem; width: 1.5rem; text-align: center; }
    .step-done .step-icon::before { content: "✅"; }
    .step-active .step-icon::before { content: "⏳"; }
    .step-pending .step-icon::before { content: "○"; }
    .step-done { color: var(--text-primary); }
    .step-active { color: var(--text-primary); font-weight: 500; }
    .actions { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 2rem; }
    .error-msg { color: var(--danger); margin-top: 1.5rem; }
    .hidden { display: none; }
  </style>
</head>
<body>
  <div class="notebook-page">
    <a class="back-link" href="javascript:history.back()">← Back</a>
    <h1 id="page-title">Generating Notebook…</h1>
    <p class="subtitle" id="subtitle">Powered by Kimi K2.5</p>

    <ul class="progress-list" id="progress">
      <li id="step-fetching_pdf" class="step-pending">
        <span class="step-icon"></span><span>Fetching PDF from arXiv</span>
      </li>
      <li id="step-analysing" class="step-pending">
        <span class="step-icon"></span><span>Analysing paper structure</span>
      </li>
      <li id="step-designing" class="step-pending">
        <span class="step-icon"></span><span>Designing notebook layout</span>
      </li>
      <li id="step-generating" class="step-pending">
        <span class="step-icon"></span><span>Generating code cells</span>
      </li>
    </ul>

    <div id="error-area" class="hidden error-msg"></div>

    <div id="actions" class="actions hidden">
      <button id="btn-download" class="btn btn-primary">Download .ipynb</button>
      <button id="btn-colab" class="btn">Open in Colab</button>
    </div>
  </div>

  <script>
    const params = new URLSearchParams(location.search);
    const itemId = params.get('item_id');
    const STEPS = ['fetching_pdf', 'analysing', 'designing', 'generating'];
    let notebookBlob = null;
    let notebookTitle = 'notebook';

    function setStepState(stepId, state) {
      const el = document.getElementById(`step-${stepId}`);
      if (!el) return;
      el.className = `step-${state}`;
    }

    function markPreviousStepsDone(currentStep) {
      const idx = STEPS.indexOf(currentStep);
      STEPS.slice(0, idx).forEach(s => setStepState(s, 'done'));
      setStepState(currentStep, 'active');
    }

    if (!itemId) {
      document.getElementById('error-area').textContent = 'Missing item_id parameter.';
      document.getElementById('error-area').classList.remove('hidden');
    } else {
      fetch(`/api/items/${itemId}/notebook`, { method: 'POST' })
        .then((resp) => {
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const reader = resp.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          function pump() {
            return reader.read().then(({ done, value }) => {
              if (done) return;
              buffer += decoder.decode(value, { stream: true });
              const lines = buffer.split('\n');
              buffer = lines.pop();
              lines.forEach(line => {
                if (!line.startsWith('data: ')) return;
                const event = JSON.parse(line.slice(6));
                handleEvent(event);
              });
              return pump();
            });
          }
          return pump();
        })
        .catch((err) => {
          document.getElementById('error-area').textContent = `Error: ${err.message}`;
          document.getElementById('error-area').classList.remove('hidden');
        });
    }

    function handleEvent(event) {
      if (event.status === 'error') {
        document.getElementById('error-area').textContent = `Error: ${event.message}`;
        document.getElementById('error-area').classList.remove('hidden');
        return;
      }

      if (event.status === 'done') {
        STEPS.forEach(s => setStepState(s, 'done'));
        notebookTitle = (event.title || 'notebook').replace(/[^a-z0-9]/gi, '_').toLowerCase();
        const bytes = atob(event.notebook_b64);
        const arr = new Uint8Array(bytes.length);
        for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
        notebookBlob = new Blob([arr], { type: 'application/json' });

        document.getElementById('page-title').textContent = event.title || 'Notebook Ready';
        document.getElementById('subtitle').textContent = 'Your notebook is ready to download.';
        document.getElementById('actions').classList.remove('hidden');
        return;
      }

      markPreviousStepsDone(event.status);
    }

    document.getElementById('btn-download')?.addEventListener('click', () => {
      if (!notebookBlob) return;
      const url = URL.createObjectURL(notebookBlob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${notebookTitle}.ipynb`;
      a.click();
      URL.revokeObjectURL(url);
    });

    document.getElementById('btn-colab')?.addEventListener('click', () => {
      if (!notebookBlob) return;
      // Colab supports opening a notebook from a GitHub gist URL.
      // Without a gist, we trigger a download and prompt the user to upload.
      alert('Download the .ipynb file first, then upload it at colab.research.google.com via File → Upload notebook.');
      document.getElementById('btn-download').click();
    });

    // Apply saved theme
    const theme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', theme);
  </script>
</body>
</html>
```

- [ ] **Step 2: Verify the page loads**

Open: `http://127.0.0.1:8000/notebook?item_id=1`

Expected: progress list renders; if no paper item in DB you'll see a 404 fetch error in the error area — correct at this stage.

- [ ] **Step 3: Commit**

```bash
git add static/notebook.html
git commit -m "feat: add paper-to-notebook static page with SSE progress"
```

---

## Task 8: Paper action buttons in item card

**Files:**
- Modify: `static/js/components.js`
- Modify: `static/css/style.css`

- [ ] **Step 1: Add paper action styles to `static/css/style.css`**

Append at the end of the file:

```css
/* ========== Paper Action Buttons ========== */
.paper-actions {
  display: flex;
  gap: 0.4rem;
  margin-left: auto;
  flex-shrink: 0;
}

.btn-summary {
  color: var(--accent-text);
  border-color: var(--accent-light);
  background: var(--accent-light);
}

.btn-summary:hover {
  background: var(--accent);
  color: var(--text-inverse);
  border-color: var(--accent);
}

.btn-notebook {
  color: var(--success);
  border-color: var(--success-light);
  background: var(--success-light);
}

.btn-notebook:hover {
  background: var(--success);
  color: var(--text-inverse);
  border-color: var(--success);
}
```

- [ ] **Step 2: Add paper action buttons to `renderItemCard` in `static/js/components.js`**

In `renderItemCard`, the current card structure is:

```html
<div class="item-card">
  <div class="item-score ${cls}">${score}%</div>
  <div class="item-content">
    ...
  </div>
</div>
```

Replace the return template so the `item-card` div uses `position: relative` layout and adds the buttons for paper items. Find the return template string starting with `return \`` and replace it:

```javascript
export function renderItemCard(item, sourcesMap = {}) {
  const score = Math.round((item.relevance_score || 0) * 100);
  const cls = scoreClass(item.relevance_score || 0);
  const source = sourcesMap[item.source_id];
  const sourceName = source ? source.name : `Source #${item.source_id}`;
  const domain = getDomain(item.url);

  const paperActions = item.content_type === "paper" ? `
    <div class="paper-actions">
      <a href="/summary?item_id=${item.id}" target="_blank" rel="noopener"
         class="btn btn-sm btn-summary">Summary</a>
      <a href="/notebook?item_id=${item.id}" target="_blank" rel="noopener"
         class="btn btn-sm btn-notebook">Notebook</a>
    </div>` : "";

  return `
    <div class="item-card">
      <div class="item-score ${cls}">${score}%</div>
      <div class="item-content">
        <div style="display:flex;align-items:flex-start;gap:0.5rem">
          <a class="item-title" href="${escapeHtml(item.url)}" target="_blank" rel="noopener"
             style="flex:1">
            ${escapeHtml(item.title)}
          </a>
          ${paperActions}
        </div>
        ${item.summary ? `<div class="item-summary">${escapeHtml(item.summary)}</div>` : ""}
        <div class="item-meta">
          ${item.author ? `<span class="item-author">${escapeHtml(item.author)}</span><span class="item-meta-divider"></span>` : ""}
          <span>${sourceName}</span>
          <span class="item-meta-divider"></span>
          <span>${domain}</span>
          ${item.published_at ? `<span class="item-meta-divider"></span><span>${formatDate(item.published_at)}</span>` : ""}
          ${item.points != null ? `<span class="item-meta-divider"></span><span>${item.points} pts</span>` : ""}
          ${item.comment_count != null ? `<span class="item-meta-divider"></span><span>${item.comment_count} comments</span>` : ""}
        </div>
        <div class="item-tags">
          <span class="tag tag-source">${escapeHtml(sourceName)}</span>
          <span class="tag ${typeTagClass(item.content_type)}">${item.content_type}</span>
        </div>
      </div>
    </div>
  `;
}
```

- [ ] **Step 3: Manually verify in browser**

With the server running and some paper items in the DB (sync `hf-papers` or `arxiv-csai`), open `http://127.0.0.1:8000`. Paper cards should show Summary and Notebook buttons top-right. Non-paper cards should not.

- [ ] **Step 4: Commit**

```bash
git add static/js/components.js static/css/style.css
git commit -m "feat: add Summary and Notebook buttons to paper item cards"
```

---

## Task 9: End-to-end smoke test

- [ ] **Step 1: Sync a paper source**

```bash
curl -X POST http://127.0.0.1:8000/api/sources/sync/hf-papers
```

Expected: `{"source":"hf-papers","fetched":N,"new":N,...}`

- [ ] **Step 2: Get a paper item ID**

```bash
.venv/bin/python -c "
import asyncio
from sqlalchemy import select
from app.database import async_session
from app.models.item import Item, ContentType

async def main():
    async with async_session() as db:
        r = await db.execute(select(Item).where(Item.content_type==ContentType.PAPER).limit(3))
        for i in r.scalars():
            print(i.id, i.url, i.title[:50])
asyncio.run(main())
"
```

Note an item ID from the output.

- [ ] **Step 3: Test summary endpoint**

Replace `{ID}` with an actual ID:

```bash
curl -s "http://127.0.0.1:8000/api/items/{ID}/summary" | python3 -m json.tool | head -20
```

Expected: JSON with `item_id`, `title`, `summary` fields. Requires `KIMI_API_KEY` set in `.env`.

- [ ] **Step 4: Verify summary page**

Open `http://127.0.0.1:8000/summary?item_id={ID}` — should render title and summary text.

- [ ] **Step 5: Verify notebook page**

Open `http://127.0.0.1:8000/notebook?item_id={ID}` — should animate through all 4 progress steps (takes ~60-120s), then show Download + Colab buttons.

- [ ] **Step 6: Push to GitHub**

```bash
TOKEN=$(gh auth token) && git -c credential.helper= \
  -c "credential.helper=!f() { echo username=x-access-token; echo password=$TOKEN; }; f" \
  push origin main
```

---

## Self-Review Checklist

- [x] Spec coverage: config ✓, kimi service ✓, arxiv service ✓, notebook builder ✓, summary endpoint ✓, notebook SSE endpoint ✓, summary.html ✓, notebook.html ✓, components.js buttons ✓, style.css ✓
- [x] No placeholders: all code blocks contain complete implementations
- [x] Type consistency: `call_kimi(system, user, max_tokens)` used consistently in Tasks 2, 4, 5; `fetch_abstract`, `fetch_pdf_bytes`, `arxiv_id_from_url`, `pdf_url_from_arxiv_url` defined in Task 3 and used in Task 5
- [x] `_get_paper_item` defined in `paper_tools.py` Task 5 and referenced in tests Task 5
- [x] `build_notebook` is an `AsyncIterator` — iterated with `async for` in `paper_tools.py` ✓
