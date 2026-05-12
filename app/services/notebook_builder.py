"""Three-stage LLM pipeline to convert a research paper PDF into a Jupyter notebook.

Stage 1 — Analyse: extract structured paper metadata from raw text.
Stage 2 — Design: plan the toy implementation structure.
Stage 3 — Generate: produce cell-by-cell notebook content.
"""
from __future__ import annotations

import base64
import json
from collections.abc import Callable, Coroutine
from typing import Any, AsyncIterator

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from app.services.pdf_utils import extract_pdf_text, parse_json_response

CallLLMFn = Callable[..., Coroutine[Any, Any, str]]

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


async def build_notebook(pdf_bytes: bytes, call_llm_fn: CallLLMFn) -> AsyncIterator[dict]:
    """Three-stage pipeline. Yields status dicts; final yield contains notebook_b64."""
    yield {"status": "analysing"}
    paper_text = extract_pdf_text(pdf_bytes)
    analysis_raw = await call_llm_fn(
        system=SYSTEM_PROMPT,
        user=ANALYSIS_PROMPT.replace("{paper_text}", paper_text),
        max_tokens=8192,
    )
    analysis = parse_json_response(analysis_raw)

    yield {"status": "designing"}
    design_raw = await call_llm_fn(
        system=SYSTEM_PROMPT,
        user=DESIGN_PROMPT.replace("{analysis_json}", json.dumps(analysis, indent=2)),
        max_tokens=8192,
    )
    design = parse_json_response(design_raw)

    yield {"status": "generating"}
    cells_raw = await call_llm_fn(
        system=SYSTEM_PROMPT,
        user=GENERATE_PROMPT.replace("{analysis_json}", json.dumps(analysis, indent=2)).replace(
            "{design_json}", json.dumps(design, indent=2)
        ),
        max_tokens=32768,
    )
    cells_data = parse_json_response(cells_raw)
    notebook_json = _assemble_notebook(cells_data.get("cells", []))
    notebook_b64 = base64.b64encode(notebook_json.encode()).decode()

    title = analysis.get("title", "notebook")
    yield {"status": "done", "notebook_b64": notebook_b64, "title": title}
