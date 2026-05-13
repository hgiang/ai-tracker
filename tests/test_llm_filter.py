import pytest

from app.services import llm_filter
from app.services.llm_client import Provider
from app.services.llm_filter import CandidateItem, rerank_candidates


@pytest.fixture
def candidates():
    return [
        CandidateItem(id=1, title="New distillation paper", source="arxiv", summary="LoRA distill"),
        CandidateItem(id=2, title="Crypto + AI fund launches", source="reddit", summary="web3"),
        CandidateItem(id=3, title="Agentic RAG tutorial", source="hn", summary="tool use"),
    ]


@pytest.mark.asyncio
async def test_rerank_parses_json_array(monkeypatch, candidates):
    response = (
        '[{"id": 1, "keep": true, "reason": "matches: distillation"},'
        ' {"id": 2, "keep": false, "reason": "skip: crypto crossover"},'
        ' {"id": 3, "keep": true, "reason": "matches: agentic, RAG"}]'
    )

    async def fake_call_llm(**kwargs):
        return response

    monkeypatch.setattr(llm_filter, "call_llm", fake_call_llm)

    verdicts = await rerank_candidates(
        candidates, "prefs", provider=Provider.OPENAI, api_key="sk-test"
    )
    assert [v.kept for v in verdicts] == [True, False, True]
    assert verdicts[1].reason.startswith("skip")


@pytest.mark.asyncio
async def test_rerank_strips_code_fences(monkeypatch, candidates):
    response = '```json\n[{"id":1,"keep":true,"reason":"ok"},{"id":2,"keep":false,"reason":"no"},{"id":3,"keep":true,"reason":"ok"}]\n```'

    async def fake_call_llm(**kwargs):
        return response

    monkeypatch.setattr(llm_filter, "call_llm", fake_call_llm)
    verdicts = await rerank_candidates(
        candidates, "prefs", provider=Provider.OPENAI, api_key="sk-test"
    )
    assert len(verdicts) == 3


@pytest.mark.asyncio
async def test_missing_verdict_defaults_to_keep(monkeypatch, candidates):
    response = '[{"id": 1, "keep": true, "reason": "ok"}]'  # ids 2 and 3 missing

    async def fake_call_llm(**kwargs):
        return response

    monkeypatch.setattr(llm_filter, "call_llm", fake_call_llm)
    verdicts = await rerank_candidates(
        candidates, "prefs", provider=Provider.OPENAI, api_key="sk-test"
    )
    assert [v.item_id for v in verdicts] == [1, 2, 3]
    assert verdicts[1].kept is True
    assert verdicts[1].reason == "(not judged)"


@pytest.mark.asyncio
async def test_empty_input_short_circuits(monkeypatch):
    async def fake_call_llm(**kwargs):  # pragma: no cover - should not run
        raise AssertionError("LLM should not be called for empty input")

    monkeypatch.setattr(llm_filter, "call_llm", fake_call_llm)
    assert await rerank_candidates([], "prefs", provider=Provider.OPENAI, api_key="sk") == []
