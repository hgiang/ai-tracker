"""Three-phase LLM pipeline to produce a peer-review-quality analysis of a research paper.

Phase 1 — Comprehend: extract paper metadata and key claims from raw text.
Phase 2 — Analyse:    assess methodology, identify strengths/weaknesses, rate contribution.
Phase 3 — Synthesise: produce the final structured review in Markdown.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from typing import Any, AsyncIterator

from app.services.pdf_utils import extract_pdf_text, parse_json_response

CallLLMFn = Callable[..., Coroutine[Any, Any, str]]

REVIEW_SYSTEM = (
    "You are a rigorous academic peer reviewer with deep expertise across machine learning, "
    "AI systems, and related fields. You follow the review standards of top-tier venues "
    "such as NeurIPS, ICML, and Nature. Your reviews are evidence-based, constructive, "
    "and specific — always referencing exact sections, figures, or tables in the paper."
)

COMPREHENSION_PROMPT = """\
Read the research paper text below and extract structured metadata and key claims.

Return a JSON object with exactly these fields:
{
  "title": "Full paper title",
  "authors": "Author list as a single string",
  "venue": "Publication venue or preprint server (e.g. arXiv, NeurIPS 2024)",
  "year": "Year as a string",
  "domain": "Research field and subfield",
  "paper_type": "empirical|theoretical|survey|systems|position",
  "problem_statement": "What problem does the paper solve? (2-3 sentences)",
  "methodology_summary": "How does the paper approach the problem? (2-3 sentences)",
  "claims": [
    {
      "claim": "Specific claim about a contribution or finding",
      "evidence": "What evidence in the paper supports this claim",
      "strength": "Strong|Moderate|Weak"
    }
  ]
}

Paper text:
{paper_text}
"""

ANALYSIS_PROMPT = """\
Given the paper comprehension below, perform a rigorous critical analysis.

Return a JSON object with exactly these fields:
{
  "methodology_ratings": {
    "soundness":           {"rating": 3, "justification": "..."},
    "novelty":             {"rating": 3, "justification": "..."},
    "reproducibility":     {"rating": 3, "justification": "..."},
    "experimental_design": {"rating": 3, "justification": "..."},
    "statistical_rigor":   {"rating": 3, "justification": "..."},
    "scalability":         {"rating": 3, "justification": "..."}
  },
  "strengths": [
    {"title": "...", "detail": "...", "reference": "section/figure/table reference"}
  ],
  "weaknesses": [
    {"title": "...", "detail": "...", "impact": "...", "suggestion": "..."}
  ],
  "contribution_level": "Landmark|Significant|Moderate|Marginal|Below threshold",
  "overall_assessment": "Accept|Weak Accept|Borderline|Weak Reject|Reject",
  "confidence": "High|Medium|Low",
  "confidence_justification": "Why you are confident or not in this assessment",
  "questions_for_authors": ["Question 1", "Question 2", "Question 3"],
  "literature_positioning": "2-3 sentences on how this work relates to state of the art",
  "minor_issues": ["issue 1", "issue 2"]
}

Rate each methodology criterion 1–5 (1 = very poor, 5 = excellent).
Provide at least 3 strengths and 3 weaknesses, each with specific paper references.

Paper comprehension:
{comprehension_json}
"""

_SYNTHESIS_TEMPLATE = """\
Given the paper comprehension and critical analysis below, write a complete structured peer review in Markdown.

Use this exact structure (fill in bracketed guidance):

# Paper Review: TITLE

## Paper Metadata
- **Authors**: AUTHORS
- **Venue**: VENUE
- **Year**: YEAR
- **Domain**: DOMAIN
- **Paper Type**: PAPER_TYPE

## Executive Summary

[2-3 paragraphs covering: what the paper does, your overall assessment, and the key balance of strengths and weaknesses]

## Summary of Contributions

[Numbered list — one sentence per claimed contribution]

## Strengths

### S1: [title]
[Detail with specific section/figure/table reference, and why it matters]

### S2: [title]
[...]

### S3: [title]
[...]

## Weaknesses

### W1: [title]
[Detail, impact on the paper's claims, and an actionable suggestion to fix it]

### W2: [title]
[...]

### W3: [title]
[...]

## Methodology Assessment

| Criterion | Rating (1-5) | Assessment |
|-----------|:---:|------------|
| Soundness | X | [justification] |
| Novelty | X | [justification] |
| Reproducibility | X | [justification] |
| Experimental Design | X | [justification] |
| Statistical Rigor | X | [justification] |
| Scalability | X | [justification] |

## Questions for the Authors

1. [Specific question targeting a genuine ambiguity or methodology choice]
2. [...]
3. [...]

## Minor Issues

- [Typo, formatting issue, missing reference, or clarity suggestion]

## Literature Positioning

[Paragraph on how this work relates to the current state of the art, and what important related work is missing]

## Recommendations

**Overall Assessment**: OVERALL_ASSESSMENT
**Confidence**: CONFIDENCE — CONFIDENCE_JUSTIFICATION
**Contribution Level**: CONTRIBUTION_LEVEL

### Actionable Suggestions for Improvement
1. [Specific, constructive suggestion]
2. [...]
3. [...]

---
Output only the Markdown review. No preamble or trailing text.

Paper comprehension:
COMPREHENSION_JSON

Critical analysis:
ANALYSIS_JSON
"""


def _build_synthesis_prompt(comprehension: dict, analysis: dict) -> str:
    return (
        _SYNTHESIS_TEMPLATE
        .replace("TITLE", comprehension.get("title", ""))
        .replace("AUTHORS", comprehension.get("authors", ""))
        .replace("VENUE", comprehension.get("venue", ""))
        .replace("YEAR", str(comprehension.get("year", "")))
        .replace("DOMAIN", comprehension.get("domain", ""))
        .replace("PAPER_TYPE", comprehension.get("paper_type", ""))
        .replace(
            "OVERALL_ASSESSMENT",
            analysis.get("overall_assessment", ""),
        )
        .replace("CONFIDENCE_JUSTIFICATION", analysis.get("confidence_justification", ""))
        .replace("CONFIDENCE", analysis.get("confidence", ""))
        .replace("CONTRIBUTION_LEVEL", analysis.get("contribution_level", ""))
        .replace("COMPREHENSION_JSON", json.dumps(comprehension, indent=2))
        .replace("ANALYSIS_JSON", json.dumps(analysis, indent=2))
    )


async def build_review(pdf_bytes: bytes, call_llm_fn: CallLLMFn) -> AsyncIterator[dict]:
    """Three-phase pipeline: comprehend → analyse → synthesise.

    Yields status dicts throughout; the final yield has `status="done"` with
    `review` (Markdown string) and `title` keys.
    """
    yield {"status": "comprehending"}
    paper_text = extract_pdf_text(pdf_bytes)
    comprehension_raw = await call_llm_fn(
        system=REVIEW_SYSTEM,
        user=COMPREHENSION_PROMPT.replace("{paper_text}", paper_text),
        max_tokens=4096,
    )
    comprehension = parse_json_response(comprehension_raw)

    yield {"status": "analysing"}
    analysis_raw = await call_llm_fn(
        system=REVIEW_SYSTEM,
        user=ANALYSIS_PROMPT.replace(
            "{comprehension_json}", json.dumps(comprehension, indent=2)
        ),
        max_tokens=4096,
    )
    analysis = parse_json_response(analysis_raw)

    yield {"status": "synthesising"}
    review_markdown = await call_llm_fn(
        system=REVIEW_SYSTEM,
        user=_build_synthesis_prompt(comprehension, analysis),
        max_tokens=8192,
    )

    yield {
        "status": "done",
        "review": review_markdown,
        "title": comprehension.get("title", "paper"),
    }
