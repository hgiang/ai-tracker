"""AI Tracker agent: a tool-calling loop over the local item corpus.

Uses the OpenAI-compatible chat completions API (Kimi by default) and
dispatches model-issued tool calls to the implementations in
`app.agent.tools`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import search_items
from app.models.item import ContentType
from app.services.kimi import _get_client
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are AI Tracker, a research assistant for a personal AI news aggregator.

The user follows AI/ML and wants concise, source-grounded answers. The local
corpus contains items ingested from Hacker News, Reddit (r/MachineLearning,
r/LocalLLaMA), arXiv (cs.AI, cs.CL), GitHub trending, and AI-lab RSS feeds
(OpenAI, Anthropic, Google AI, Hugging Face).

Operating rules:
1. Always call `search_items` before answering any factual question about
   recent AI news, papers, or repos. Do not answer from prior knowledge alone.
2. Prefer specific, narrow queries. If the first search is too broad, refine
   with `content_type` (paper/news/repo/discussion) or `min_score`.
3. Cite items by title and URL. Never fabricate titles, authors, or URLs.
4. If `search_items` returns zero results, say so plainly and suggest a
   broader query — do not invent items.
5. Keep answers tight: a one-line summary, then a bulleted list of the
   most relevant items (title, source, one-sentence why-it-matters, URL).
6. If the user asks something the local corpus cannot answer (e.g. "what
   happened today on Twitter"), say the corpus does not cover it.
"""


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_items",
            "description": (
                "Search the local AI news corpus by keyword and filters. "
                "Returns ranked items with title, summary, URL, source, and "
                "relevance score."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text query matched against title and summary.",
                    },
                    "content_type": {
                        "type": "string",
                        "enum": [c.value for c in ContentType],
                        "description": "Restrict to one content type.",
                    },
                    "source_id": {
                        "type": "integer",
                        "description": "Restrict to a single source id.",
                    },
                    "min_score": {
                        "type": "number",
                        "description": "Minimum relevance_score (0.0-1.0).",
                    },
                    "page": {"type": "integer", "minimum": 1, "default": 1},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 10,
                    },
                },
                "required": [],
            },
        },
    }
]


@dataclass(frozen=True)
class AgentResult:
    answer: str
    tool_calls: tuple[dict[str, Any], ...]


async def _dispatch_tool(
    name: str, arguments: dict[str, Any], db: AsyncSession
) -> dict[str, Any]:
    if name == "search_items":
        ct = arguments.get("content_type")
        result = await search_items(
            db,
            query=arguments.get("query"),
            content_type=ContentType(ct) if ct else None,
            source_id=arguments.get("source_id"),
            min_score=arguments.get("min_score"),
            page=arguments.get("page", 1),
            limit=arguments.get("limit", 10),
        )
        return result.model_dump(mode="json")
    raise ValueError(f"Unknown tool: {name}")


async def run_agent(
    user_message: str,
    db: AsyncSession,
    *,
    max_turns: int = 5,
) -> AgentResult:
    """Run a tool-calling loop until the model returns a final message."""
    if not settings.kimi_api_key:
        raise ValueError("KIMI_API_KEY is not configured")

    client = _get_client()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    tool_calls_made: list[dict[str, Any]] = []

    for _ in range(max_turns):
        response = await client.chat.completions.create(
            model=settings.kimi_model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        msg = response.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            return AgentResult(
                answer=msg.content or "",
                tool_calls=tuple(tool_calls_made),
            )

        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            try:
                output = await _dispatch_tool(call.function.name, args, db)
                tool_calls_made.append(
                    {"name": call.function.name, "arguments": args, "ok": True}
                )
            except Exception as exc:  # surface tool errors back to the model
                logger.exception("Tool %s failed", call.function.name)
                output = {"error": str(exc)}
                tool_calls_made.append(
                    {"name": call.function.name, "arguments": args, "ok": False}
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(output, default=str),
                }
            )

    return AgentResult(
        answer="(agent hit max_turns without producing a final answer)",
        tool_calls=tuple(tool_calls_made),
    )
