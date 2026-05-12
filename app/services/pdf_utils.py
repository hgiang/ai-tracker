"""Shared PDF text extraction and JSON response parsing utilities."""
from __future__ import annotations

import json
import re

import fitz


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = 40_000) -> str:
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


def parse_json_response(text: str) -> dict:
    """Extract the first complete JSON object from an LLM response string.

    Handles markdown code fences and leading/trailing prose by walking the
    character stream to find the first balanced {…} block.
    """
    text = re.sub(r"```(?:json)?\s*", "", text)
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in response: {text[:200]}")
    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError(f"No complete JSON object found in response: {text[:200]}")
