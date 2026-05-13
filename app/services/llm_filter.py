"""LLM-based re-ranking of digest candidates against user preferences."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Sequence

from app.services.llm_client import Provider, call_llm

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CandidateItem:
    """Minimal projection of an Item needed for re-ranking."""

    id: int
    title: str
    source: str
    summary: str | None


@dataclass(frozen=True)
class FilterVerdict:
    item_id: int
    kept: bool
    reason: str


SYSTEM_PROMPT = """\
You are a curator for a personal AI news digest. The user's preferences are
provided verbatim below. Your job is to judge a batch of candidate items and
decide which match the preferences.

Rules:
- Respect "Topics to skip" strictly — those items must be rejected.
- For each item, return a one-sentence reason grounded in the preferences.
- Be specific in the reason (e.g. "matches: agentic AI, tool use"); avoid
  generic phrases like "looks interesting".
- Output ONLY a JSON array, no preamble or trailing text.

Output schema:
[
  {"id": <int>, "keep": <bool>, "reason": "<one short sentence>"},
  ...
]
"""

USER_TEMPLATE = """\
# Preferences

{preferences}

# Candidates

{candidates}

Return a JSON array with one object per candidate, preserving the ids.
"""


def _format_candidates(items: Sequence[CandidateItem]) -> str:
    lines: list[str] = []
    for item in items:
        summary = (item.summary or "").strip().replace("\n", " ")
        if len(summary) > 400:
            summary = summary[:400] + "…"
        lines.append(
            f"- id={item.id} | source={item.source} | title={item.title}\n"
            f"  summary: {summary or '(none)'}"
        )
    return "\n".join(lines)


def _extract_json_array(text: str) -> list[dict]:
    """Pull the first JSON array out of an LLM response, tolerating prose."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", stripped, flags=re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, list):
        raise ValueError("LLM did not return a JSON array")
    return data


async def rerank_candidates(
    items: Sequence[CandidateItem],
    preferences: str,
    *,
    provider: Provider,
    api_key: str,
    max_tokens: int = 4096,
) -> list[FilterVerdict]:
    """Ask the LLM to keep/drop each candidate against the preferences.

    Single batched call. Items the model doesn't return are treated as kept
    with a neutral reason so a partial response never silently drops content.
    """
    if not items:
        return []

    user_message = USER_TEMPLATE.format(
        preferences=preferences.strip(),
        candidates=_format_candidates(items),
    )
    raw = await call_llm(
        provider=provider,
        api_key=api_key,
        system=SYSTEM_PROMPT,
        user=user_message,
        max_tokens=max_tokens,
    )

    parsed = _extract_json_array(raw)
    verdicts_by_id: dict[int, FilterVerdict] = {}
    for entry in parsed:
        try:
            item_id = int(entry["id"])
            kept = bool(entry["keep"])
            reason = str(entry.get("reason") or "").strip()
        except (KeyError, TypeError, ValueError):
            logger.warning("Skipping malformed verdict entry: %r", entry)
            continue
        verdicts_by_id[item_id] = FilterVerdict(
            item_id=item_id, kept=kept, reason=reason or "(no reason given)"
        )

    results: list[FilterVerdict] = []
    for item in items:
        verdict = verdicts_by_id.get(item.id)
        if verdict is None:
            logger.warning("LLM did not return a verdict for item %s — keeping as-is", item.id)
            verdict = FilterVerdict(item_id=item.id, kept=True, reason="(not judged)")
        results.append(verdict)
    return results
