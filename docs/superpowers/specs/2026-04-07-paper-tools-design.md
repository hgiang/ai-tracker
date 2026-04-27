# Paper Tools: Summary & Notebook — Design Spec
_2026-04-07_

## Overview

Add two action buttons (Summary, Notebook) to paper item cards in the AI tracker feed. Each opens a new browser tab with a dedicated page. Both pages call FastAPI backend endpoints that use the item's stored arXiv URL to fetch content and call the Kimi K2.5 LLM API.

---

## Configuration

Add to `app/config.py`:
```python
kimi_api_key: str = ""
kimi_base_url: str = "https://api.moonshot.ai/v1"
kimi_model: str = "kimi-k2.5"
```

Add to `.env` / `.env.example`:
```
KIMI_API_KEY=your_key_here
KIMI_BASE_URL=https://api.moonshot.ai/v1
KIMI_MODEL=kimi-k2.5
```

Dependency: add `openai>=1.0.0` and `nbformat>=5.0` and `pymupdf>=1.24.0` to `pyproject.toml`.

---

## Backend

### New file: `app/routes/paper_tools.py`

Registered under prefix `/api/items` in `app/main.py`.

#### `GET /api/items/{item_id}/summary`

1. Fetch item from DB; 404 if not found or `content_type != PAPER`.
2. Check `item.metadata_json["llm_summary"]` — if present, return cached value immediately.
3. Fetch arXiv abstract: `GET https://export.arxiv.org/abs/{arxiv_id}` (derive `arxiv_id` from `item.url`, e.g. `arxiv.org/abs/2501.12345` → `2501.12345`). Parse abstract text from response HTML (`<blockquote class="abstract">`).
4. Build prompt: title + abstract + "Summarise this paper in 3-5 paragraphs for an ML practitioner..."
5. Call Kimi K2.5 via `openai.AsyncOpenAI(base_url=..., api_key=...)`.
6. Cache result in `item.metadata_json["llm_summary"]`, persist to DB.
7. Return `{"item_id": int, "title": str, "summary": str}`.

Error handling: if arXiv fetch fails, fall back to `item.summary` (stored abstract snippet). If Kimi call fails, return 502 with message.

#### `POST /api/items/{item_id}/notebook`

Streams Server-Sent Events (SSE) using `fastapi.responses.StreamingResponse` with `text/event-stream`.

Steps emitted as SSE `data:` lines:
1. `{"status": "fetching_pdf"}` — derive PDF URL (`arxiv.org/abs/ID` → `arxiv.org/pdf/ID`), download with `httpx`.
2. `{"status": "analysing"}` — Stage 1: send PDF text to Kimi with `ANALYSIS_PROMPT` (adapted from paper-to-notebook), get structured JSON back.
3. `{"status": "designing"}` — Stage 2: send analysis JSON to Kimi with `DESIGN_PROMPT`, get notebook structure JSON.
4. `{"status": "generating"}` — Stage 3: send design to Kimi with `GENERATE_PROMPT`, get cell-by-cell code/markdown.
5. `{"status": "done", "notebook_b64": "<base64-encoded .ipynb>"}` — assemble notebook with `nbformat`, base64-encode, send in final event.

PDF text extraction: use `pymupdf` (`fitz`) to extract text from the downloaded PDF bytes.

Notebook assembly: use `nbformat.v4` (`new_notebook`, `new_code_cell`, `new_markdown_cell`).

Error: emit `{"status": "error", "message": "..."}` and close stream.

---

## Frontend

### `static/summary.html`

- Reads `?item_id=` from URL query string.
- On load: calls `GET /api/items/{item_id}/summary`, shows spinner while loading.
- Renders: paper title as `<h1>`, summary text as formatted paragraphs (light markdown rendering reusing `renderMarkdown` from `components.js`).
- Minimal standalone page — no nav, just content + back link.

### `static/notebook.html`

- Reads `?item_id=` from URL query string.
- On load: calls `POST /api/items/{item_id}/notebook` and reads the SSE stream.
- Shows a progress list that fills in as each status event arrives:
  - ⏳ Fetching PDF…
  - ⏳ Analysing paper…
  - ⏳ Designing notebook structure…
  - ⏳ Generating code cells…
- On `done` event: decode base64 → create a `Blob` → show two buttons:
  - **Download .ipynb** — triggers browser download.
  - **Open in Colab** — encodes notebook as `data:` URI and opens `https://colab.research.google.com/notebook#create=true&...` (or uses the standard Colab file-upload URL pattern).
- On `error` event: show error message in red.

### `static/js/components.js` — `renderItemCard` update

Add paper action buttons inside the card when `item.content_type === "paper"`:

```html
<div class="paper-actions">
  <a href="/summary.html?item_id={id}" target="_blank" class="btn btn-sm btn-summary">Summary</a>
  <a href="/notebook.html?item_id={id}" target="_blank" class="btn btn-sm btn-notebook">Notebook</a>
</div>
```

Buttons positioned top-right of the card via CSS flexbox.

---

## Data Flow

```
User clicks Summary
  → summary.html?item_id=42
  → GET /api/items/42/summary
      → DB lookup
      → arXiv abstract fetch (export.arxiv.org)
      → Kimi K2.5 call
      → cache in metadata_json
  → render markdown summary

User clicks Notebook
  → notebook.html?item_id=42
  → POST /api/items/42/notebook  (SSE stream)
      → PDF download (arxiv.org/pdf/...)
      → pymupdf text extraction
      → Kimi Stage 1: analyse
      → Kimi Stage 2: design
      → Kimi Stage 3: generate
      → nbformat assembly
      → base64 encode → SSE done event
  → Download .ipynb / Open in Colab
```

---

## Files Changed / Created

| File | Change |
|------|--------|
| `app/config.py` | Add `kimi_api_key`, `kimi_base_url`, `kimi_model` |
| `.env` / `.env.example` | Add `KIMI_API_KEY` placeholder |
| `app/routes/paper_tools.py` | New — summary + notebook endpoints |
| `app/main.py` | Register `paper_tools` router |
| `static/summary.html` | New page |
| `static/notebook.html` | New page |
| `static/js/components.js` | Add paper action buttons to `renderItemCard` |
| `static/css/style.css` | Button styles for `.btn-summary`, `.btn-notebook`, `.paper-actions` |
| `pyproject.toml` | Add `openai`, `nbformat`, `pymupdf` deps |

---

## Out of Scope

- Non-paper items (HN, Reddit, GitHub) do not get these buttons.
- No auth on the new endpoints (consistent with rest of the app).
- No Colab OAuth — user must manually upload or use the data URI approach.
