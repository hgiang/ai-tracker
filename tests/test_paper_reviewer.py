"""Unit and integration tests for the paper review pipeline."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.item import ContentType, Item
from app.services.paper_reviewer import (
    REVIEW_SYSTEM,
    _build_synthesis_prompt,
    build_review,
)
from app.services.pdf_utils import extract_pdf_text, parse_json_response


# ---------------------------------------------------------------------------
# pdf_utils unit tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_json_response_basic():
    assert parse_json_response('{"key": "value"}') == {"key": "value"}


@pytest.mark.unit
def test_parse_json_response_with_markdown_fences():
    raw = '```json\n{"key": "value"}\n```'
    assert parse_json_response(raw) == {"key": "value"}


@pytest.mark.unit
def test_parse_json_response_ignores_surrounding_prose():
    raw = 'Here is the result:\n{"key": "value"}\nThat is all.'
    assert parse_json_response(raw) == {"key": "value"}


@pytest.mark.unit
def test_parse_json_response_handles_nested_objects():
    raw = '{"outer": {"inner": 1}}'
    assert parse_json_response(raw) == {"outer": {"inner": 1}}


@pytest.mark.unit
def test_parse_json_response_no_json_raises():
    with pytest.raises(ValueError, match="No JSON object found"):
        parse_json_response("No JSON here at all.")


@pytest.mark.unit
def test_parse_json_response_unterminated_raises():
    with pytest.raises(ValueError, match="No complete JSON object found"):
        parse_json_response('{"key": "unterminated')


@pytest.mark.unit
def test_extract_pdf_text_caps_at_max_chars():
    mock_page = MagicMock()
    mock_page.get_text.return_value = "A" * 50_000
    mock_doc = MagicMock()
    mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
    with patch("app.services.pdf_utils.fitz.open", return_value=mock_doc):
        result = extract_pdf_text(b"fake_pdf", max_chars=100)
    assert len(result) == 100
    assert result == "A" * 100


@pytest.mark.unit
def test_extract_pdf_text_stops_early_when_limit_reached():
    pages = [MagicMock(), MagicMock()]
    pages[0].get_text.return_value = "B" * 200
    pages[1].get_text.return_value = "C" * 200
    mock_doc = MagicMock()
    mock_doc.__iter__ = MagicMock(return_value=iter(pages))
    with patch("app.services.pdf_utils.fitz.open", return_value=mock_doc):
        result = extract_pdf_text(b"fake", max_chars=150)
    assert len(result) == 150
    # Second page never reached once limit exceeded on first
    pages[1].get_text.assert_not_called()


# ---------------------------------------------------------------------------
# paper_reviewer unit tests
# ---------------------------------------------------------------------------

_FAKE_COMPREHENSION: dict = {
    "title": "A Great Paper",
    "authors": "Author One, Author Two",
    "venue": "NeurIPS 2024",
    "year": "2024",
    "domain": "Natural Language Processing",
    "paper_type": "empirical",
    "problem_statement": "Solves X by doing Y.",
    "methodology_summary": "Uses Z approach on W dataset.",
    "claims": [
        {"claim": "Improves SOTA by 5%", "evidence": "Table 1", "strength": "Strong"}
    ],
}

_FAKE_ANALYSIS: dict = {
    "methodology_ratings": {
        "soundness": {"rating": 4, "justification": "Technically correct"},
        "novelty": {"rating": 3, "justification": "Incremental improvement"},
        "reproducibility": {"rating": 4, "justification": "Code released"},
        "experimental_design": {"rating": 4, "justification": "Fair baselines"},
        "statistical_rigor": {"rating": 3, "justification": "No error bars"},
        "scalability": {"rating": 3, "justification": "Not tested at scale"},
    },
    "strengths": [
        {"title": "Clear motivation", "detail": "Section 1 clearly states the gap.", "reference": "Section 1"},
        {"title": "Strong baselines", "detail": "13 baselines compared.", "reference": "Table 2"},
        {"title": "Reproducibility", "detail": "Code and data released.", "reference": "Section 5"},
    ],
    "weaknesses": [
        {"title": "Limited ablations", "detail": "Only 2 ablations.", "impact": "Unclear contribution of each component.", "suggestion": "Add ablation per component."},
        {"title": "No error bars", "detail": "Single-run results.", "impact": "Hard to assess significance.", "suggestion": "Report mean ± std over 3 seeds."},
        {"title": "Narrow evaluation", "detail": "Only English datasets.", "impact": "Unclear multilingual generalization.", "suggestion": "Test on multilingual benchmarks."},
    ],
    "contribution_level": "Moderate",
    "overall_assessment": "Weak Accept",
    "confidence": "High",
    "confidence_justification": "Well within my expertise area.",
    "questions_for_authors": [
        "How does the model perform on out-of-domain data?",
        "Why was learning rate X chosen over Y?",
        "What is the compute cost vs baseline?",
    ],
    "literature_positioning": "Related to prior work on Z. Misses citation to [X].",
    "minor_issues": ["Fig 1 caption is missing units."],
}


@pytest.mark.unit
def test_build_synthesis_prompt_includes_metadata():
    prompt = _build_synthesis_prompt(_FAKE_COMPREHENSION, _FAKE_ANALYSIS)
    assert "A Great Paper" in prompt
    assert "Author One, Author Two" in prompt
    assert "NeurIPS 2024" in prompt
    assert "2024" in prompt
    assert "empirical" in prompt


@pytest.mark.unit
def test_build_synthesis_prompt_includes_assessment_fields():
    prompt = _build_synthesis_prompt(_FAKE_COMPREHENSION, _FAKE_ANALYSIS)
    assert "Weak Accept" in prompt
    assert "High" in prompt
    assert "Moderate" in prompt


@pytest.mark.unit
def test_build_synthesis_prompt_embeds_json_blobs():
    prompt = _build_synthesis_prompt(_FAKE_COMPREHENSION, _FAKE_ANALYSIS)
    assert "Improves SOTA by 5%" in prompt
    assert "Limited ablations" in prompt


@pytest.mark.unit
async def test_build_review_yields_expected_status_sequence():
    call_count = 0

    async def fake_llm(system: str, user: str, max_tokens: int) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return json.dumps(_FAKE_COMPREHENSION)
        if call_count == 2:
            return json.dumps(_FAKE_ANALYSIS)
        return "# Paper Review: A Great Paper\n\nContent."

    with patch("app.services.paper_reviewer.extract_pdf_text", return_value="paper text"):
        events = [e async for e in build_review(b"fake", fake_llm)]

    assert [e["status"] for e in events] == [
        "comprehending",
        "analysing",
        "synthesising",
        "done",
    ]


@pytest.mark.unit
async def test_build_review_done_event_has_review_and_title():
    call_count = 0

    async def fake_llm(system: str, user: str, max_tokens: int) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return json.dumps(_FAKE_COMPREHENSION)
        if call_count == 2:
            return json.dumps(_FAKE_ANALYSIS)
        return "# Paper Review: A Great Paper\n\nFull review text."

    with patch("app.services.paper_reviewer.extract_pdf_text", return_value="paper text"):
        events = [e async for e in build_review(b"fake", fake_llm)]

    done = events[-1]
    assert done["status"] == "done"
    assert done["title"] == "A Great Paper"
    assert "# Paper Review" in done["review"]


@pytest.mark.unit
async def test_build_review_calls_llm_exactly_three_times():
    call_log: list[dict] = []

    async def fake_llm(system: str, user: str, max_tokens: int) -> str:
        call_log.append({"system": system, "max_tokens": max_tokens})
        if len(call_log) == 1:
            return json.dumps(_FAKE_COMPREHENSION)
        if len(call_log) == 2:
            return json.dumps(_FAKE_ANALYSIS)
        return "review text"

    with patch("app.services.paper_reviewer.extract_pdf_text", return_value="text"):
        async for _ in build_review(b"fake", fake_llm):
            pass

    assert len(call_log) == 3
    assert all(c["system"] == REVIEW_SYSTEM for c in call_log)
    # Synthesis stage gets the largest token budget
    assert call_log[2]["max_tokens"] > call_log[0]["max_tokens"]


@pytest.mark.unit
async def test_build_review_propagates_llm_error():
    async def failing_llm(system: str, user: str, max_tokens: int) -> str:
        raise RuntimeError("API down")

    with patch("app.services.paper_reviewer.extract_pdf_text", return_value="text"):
        with pytest.raises(RuntimeError, match="API down"):
            async for _ in build_review(b"fake", failing_llm):
                pass


# ---------------------------------------------------------------------------
# Route integration tests
# ---------------------------------------------------------------------------


@pytest.fixture
def paper_item() -> Item:
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


def _parse_sse(body: str) -> list[dict]:
    return [
        json.loads(line[len("data: "):])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


@pytest.mark.integration
async def test_review_streams_status_events(paper_item):
    call_count = 0
    llm_responses = [
        json.dumps(_FAKE_COMPREHENSION),
        json.dumps(_FAKE_ANALYSIS),
        "# Paper Review\n\nFull review.",
    ]

    async def fake_call_llm(provider, api_key, system, user, max_tokens):
        nonlocal call_count
        resp = llm_responses[call_count]
        call_count += 1
        return resp

    with (
        patch("app.routes.paper_tools._get_paper_item", return_value=paper_item),
        patch("app.routes.paper_tools.fetch_pdf_bytes", return_value=b"fake"),
        patch("app.routes.paper_tools.call_llm", side_effect=fake_call_llm),
        patch("app.services.paper_reviewer.extract_pdf_text", return_value="text"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/items/1/review",
                json={"provider": "kimi", "api_key": "test-key"},
            )

    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    statuses = [e["status"] for e in events]
    assert "fetching_pdf" in statuses
    assert "comprehending" in statuses
    assert "analysing" in statuses
    assert "synthesising" in statuses
    assert "done" in statuses


@pytest.mark.integration
async def test_review_done_event_contains_review_text(paper_item):
    call_count = 0
    llm_responses = [
        json.dumps(_FAKE_COMPREHENSION),
        json.dumps(_FAKE_ANALYSIS),
        "# Paper Review: A Great Paper\n\nExecutive summary here.",
    ]

    async def fake_call_llm(provider, api_key, system, user, max_tokens):
        nonlocal call_count
        resp = llm_responses[call_count]
        call_count += 1
        return resp

    with (
        patch("app.routes.paper_tools._get_paper_item", return_value=paper_item),
        patch("app.routes.paper_tools.fetch_pdf_bytes", return_value=b"fake"),
        patch("app.routes.paper_tools.call_llm", side_effect=fake_call_llm),
        patch("app.services.paper_reviewer.extract_pdf_text", return_value="text"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/items/1/review",
                json={"provider": "openai", "api_key": "test-key"},
            )

    done_events = [e for e in _parse_sse(resp.text) if e["status"] == "done"]
    assert len(done_events) == 1
    assert "# Paper Review" in done_events[0]["review"]
    assert done_events[0]["title"] == "A Great Paper"


@pytest.mark.integration
async def test_review_returns_404_for_non_paper():
    from fastapi import HTTPException

    with patch(
        "app.routes.paper_tools._get_paper_item",
        side_effect=HTTPException(status_code=404, detail="Item is not a paper"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/items/2/review",
                json={"provider": "kimi", "api_key": "test-key"},
            )

    assert resp.status_code == 404


@pytest.mark.integration
async def test_review_streams_error_event_on_pdf_fetch_failure(paper_item):
    with (
        patch("app.routes.paper_tools._get_paper_item", return_value=paper_item),
        patch(
            "app.routes.paper_tools.fetch_pdf_bytes",
            side_effect=RuntimeError("PDF download failed"),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/items/1/review",
                json={"provider": "kimi", "api_key": "test-key"},
            )

    assert resp.status_code == 200  # SSE always returns 200
    error_events = [e for e in _parse_sse(resp.text) if e.get("status") == "error"]
    assert len(error_events) == 1
    assert "PDF download failed" in error_events[0]["message"]
