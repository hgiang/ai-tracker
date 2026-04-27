"""Golden-set quality test for the composite scoring pipeline.

This guards against silent regressions when the scoring weights are tuned.
When you intentionally change scoring behavior, update the fixture instead
of weakening the assertion.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services.relevance import compute_composite_score

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "scoring_cases.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def _score_case(case: dict, now: datetime) -> float:
    published_at = now - timedelta(hours=case["published_hours_ago"])
    return compute_composite_score(
        title=case["title"],
        summary=case.get("summary"),
        published_at=published_at,
        points=case.get("points"),
        comment_count=case.get("comment_count"),
        source_slug=case["source_slug"],
        now=now,
    )


@pytest.fixture(scope="module")
def fixture() -> dict:
    return _load_fixture()


@pytest.mark.unit
def test_top5_contains_expected_items(fixture: dict) -> None:
    """The top-5 ranking (by set, not order) must match the golden fixture."""
    now = datetime.fromisoformat(fixture["now"])
    ranked = sorted(
        fixture["cases"],
        key=lambda c: _score_case(c, now),
        reverse=True,
    )
    top5_ids = {c["id"] for c in ranked[:5]}
    expected = set(fixture["expected_top"])
    missing = expected - top5_ids
    extra = top5_ids - expected

    assert not missing, (
        f"Expected items missing from top-5: {sorted(missing)}. "
        f"Actual top-5: {sorted(top5_ids)}"
    )
    assert not extra, (
        f"Unexpected items crept into top-5: {sorted(extra)}. "
        f"Expected: {sorted(expected)}"
    )


@pytest.mark.unit
def test_stale_viral_post_is_demoted(fixture: dict) -> None:
    """A 7-day-old post with 5000 points must not outrank a fresh frontier release."""
    now = datetime.fromisoformat(fixture["now"])
    scores = {c["id"]: _score_case(c, now) for c in fixture["cases"]}
    assert scores["old-reddit-post"] < scores["hn-gpt6-release"]
    assert scores["old-arxiv-paper"] < scores["arxiv-llm-alignment"]


@pytest.mark.unit
def test_off_topic_item_scores_lower_than_on_topic(fixture: dict) -> None:
    """Off-topic low-engagement items must score below every expected top-5 item."""
    now = datetime.fromisoformat(fixture["now"])
    off_topic = _score_case(
        next(c for c in fixture["cases"] if c["id"] == "reddit-off-topic"),
        now,
    )
    for expected_id in fixture["expected_top"]:
        case = next(c for c in fixture["cases"] if c["id"] == expected_id)
        assert _score_case(case, now) > off_topic, f"{expected_id} did not beat off-topic"
