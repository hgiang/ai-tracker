from app.adapters.x import XAdapter
from app.config import settings


class StubXAdapter(XAdapter):
    def __init__(self, responses, **kwargs):
        super().__init__("https://x.com", **kwargs)
        self._responses = list(responses)
        self.calls = []

    async def _get_json_with_headers(self, url: str, **kwargs: object):
        self.calls.append({"url": url, **kwargs})
        return self._responses.pop(0)


async def test_x_adapter_skips_when_token_missing(monkeypatch):
    monkeypatch.setattr(settings, "x_bearer_token", "")

    adapter = StubXAdapter([], accounts="karpathy")
    items, checkpoint = await adapter.fetch("123")

    assert items == []
    assert checkpoint == "123"
    assert adapter.calls == []


async def test_x_adapter_uses_newest_id_and_paginates(monkeypatch):
    monkeypatch.setattr(settings, "x_bearer_token", "test-token")

    responses = [
        (
            {
                "data": [
                    {
                        "id": "200",
                        "text": "First page tweet",
                        "created_at": "2026-03-12T10:00:00Z",
                        "author_id": "u1",
                        "public_metrics": {"like_count": 10, "reply_count": 1},
                    }
                ],
                "includes": {"users": [{"id": "u1", "username": "alice"}]},
                "meta": {"newest_id": "250", "next_token": "page-2", "result_count": 1},
            },
            {"x-rate-limit-remaining": "149", "x-rate-limit-reset": "1710240000"},
        ),
        (
            {
                "data": [
                    {
                        "id": "199",
                        "text": "Second page tweet",
                        "created_at": "2026-03-12T09:59:00Z",
                        "author_id": "u2",
                        "public_metrics": {"like_count": 4, "reply_count": 0},
                    }
                ],
                "includes": {"users": [{"id": "u2", "username": "bob"}]},
                "meta": {"result_count": 1},
            },
            {"x-rate-limit-remaining": "148", "x-rate-limit-reset": "1710240000"},
        ),
    ]
    adapter = StubXAdapter(responses, accounts="alice,bob", max_pages="2")

    items, checkpoint = await adapter.fetch("150")

    assert checkpoint == "250"
    assert [item.source_item_id for item in items] == ["200", "199"]
    assert adapter.calls[0]["params"]["since_id"] == "150"
    assert adapter.calls[0]["params"]["max_results"] == "25"
    assert "from:alice" in adapter.calls[0]["params"]["query"]
    assert adapter.calls[1]["params"]["next_token"] == "page-2"

