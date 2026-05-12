"""Tests for the tool-calling agent loop, with the LLM client mocked."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agent import agent as agent_module
from app.agent.agent import run_agent
from app.models.item import ContentType, Item
from app.models.source import Source


@pytest.fixture
async def seeded_db(db_session):
    source = Source(
        name="arXiv", slug="arxiv", adapter_type="arxiv", url="https://arxiv.org"
    )
    db_session.add(source)
    await db_session.flush()
    db_session.add(
        Item(
            source_id=source.id,
            source_item_id="2401.00001",
            url="https://arxiv.org/abs/2401.00001",
            canonical_url="https://arxiv.org/abs/2401.00001",
            title="Mixture-of-Experts scaling laws",
            normalized_title="mixture of experts scaling laws",
            summary="MoE routing improves compute-optimal training.",
            content_type=ContentType.PAPER,
            fetched_at=datetime.now(timezone.utc),
            relevance_score=0.95,
        )
    )
    await db_session.commit()
    return db_session


def _tool_call(call_id: str, name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _completion(message: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _msg(content: str | None, tool_calls: list | None = None) -> SimpleNamespace:
    m = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        role="assistant",
    )
    m.model_dump = lambda exclude_none=False: {
        k: v for k, v in {"role": "assistant", "content": content}.items()
        if not (exclude_none and v is None)
    }
    return m


@pytest.mark.asyncio
async def test_agent_calls_search_tool_then_answers(seeded_db, monkeypatch):
    monkeypatch.setattr(agent_module.settings, "kimi_api_key", "test-key")
    monkeypatch.setattr(agent_module.settings, "kimi_model", "kimi-k2.5")

    first = _msg(
        content=None,
        tool_calls=[_tool_call("c1", "search_items", '{"query": "mixture of experts"}')],
    )
    second = _msg(content="Found 1 paper on MoE scaling. See arxiv.org/abs/2401.00001.")

    mock_create = AsyncMock(side_effect=[_completion(first), _completion(second)])
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
    )

    with patch.object(agent_module, "_get_client", return_value=fake_client):
        result = await run_agent("Any new MoE papers?", seeded_db)

    assert "MoE" in result.answer or "mixture" in result.answer.lower()
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "search_items"
    assert result.tool_calls[0]["ok"] is True
    assert result.tool_calls[0]["arguments"]["query"] == "mixture of experts"
    assert mock_create.await_count == 2


@pytest.mark.asyncio
async def test_agent_returns_directly_when_no_tools_needed(seeded_db, monkeypatch):
    monkeypatch.setattr(agent_module.settings, "kimi_api_key", "test-key")

    direct = _msg(content="The corpus does not cover live Twitter feeds.")
    mock_create = AsyncMock(return_value=_completion(direct))
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
    )

    with patch.object(agent_module, "_get_client", return_value=fake_client):
        result = await run_agent("What's trending on Twitter right now?", seeded_db)

    assert "Twitter" in result.answer or "corpus" in result.answer
    assert result.tool_calls == ()


@pytest.mark.asyncio
async def test_agent_hits_max_turns(seeded_db, monkeypatch):
    monkeypatch.setattr(agent_module.settings, "kimi_api_key", "test-key")

    looping = _msg(
        content=None,
        tool_calls=[_tool_call("c1", "search_items", "{}")],
    )
    mock_create = AsyncMock(return_value=_completion(looping))
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=mock_create))
    )

    with patch.object(agent_module, "_get_client", return_value=fake_client):
        result = await run_agent("loop forever", seeded_db, max_turns=2)

    assert "max_turns" in result.answer
    assert len(result.tool_calls) == 2
