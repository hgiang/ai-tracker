import pytest

from app.adapters.rss import RSSAdapter, _needs_browser_client

SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Machine Learning</title>
  <entry>
    <id>t3_abc123</id>
    <link href="https://www.reddit.com/r/MachineLearning/comments/abc123/example/" />
    <updated>2026-04-14T03:55:00+00:00</updated>
    <title>Example Reddit entry</title>
    <author><name>/u/example</name></author>
    <content type="html">Example summary</content>
  </entry>
</feed>
"""


def test_needs_browser_client_for_reddit_hosts():
    assert _needs_browser_client("https://www.reddit.com/r/MachineLearning/hot.rss")
    assert _needs_browser_client("https://reddit.com/r/MachineLearning/hot.rss")
    assert not _needs_browser_client("https://openai.com/news/rss.xml")


@pytest.mark.asyncio
async def test_fetch_uses_browser_client_for_reddit(monkeypatch):
    adapter = RSSAdapter("https://www.reddit.com/r/MachineLearning/hot.rss")
    calls: list[str] = []

    async def fake_curl_fetch(url: str, headers: dict[str, str]) -> str:
        calls.append(url)
        assert "User-Agent" in headers
        return SAMPLE_ATOM

    async def fail_httpx_fetch(*args, **kwargs):
        raise AssertionError("httpx path should not be used for reddit feeds")

    monkeypatch.setattr("app.adapters.rss._get_text_with_curl", fake_curl_fetch)
    monkeypatch.setattr(RSSAdapter, "_get_text", fail_httpx_fetch)

    items, checkpoint = await adapter.fetch(None)

    assert calls == ["https://www.reddit.com/r/MachineLearning/hot.rss"]
    assert checkpoint == "t3_abc123"
    assert len(items) == 1
    assert items[0].title == "Example Reddit entry"


@pytest.mark.asyncio
async def test_fetch_uses_httpx_for_non_reddit(monkeypatch):
    adapter = RSSAdapter("https://openai.com/news/rss.xml")

    async def fail_curl_fetch(*args, **kwargs):
        raise AssertionError("curl path should not be used for non-reddit feeds")

    async def fake_httpx_fetch(self, url: str, **kwargs) -> str:
        assert url == "https://openai.com/news/rss.xml"
        assert kwargs["headers"]["User-Agent"]
        return SAMPLE_ATOM

    monkeypatch.setattr("app.adapters.rss._get_text_with_curl", fail_curl_fetch)
    monkeypatch.setattr(RSSAdapter, "_get_text", fake_httpx_fetch)

    items, checkpoint = await adapter.fetch(None)

    assert checkpoint == "t3_abc123"
    assert len(items) == 1
    assert items[0].source_item_id == "t3_abc123"


MULTI_ENTRY_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Machine Learning</title>
  <entry>
    <id>t3_sticky_old</id>
    <link href="https://www.reddit.com/r/MachineLearning/comments/sticky_old/pinned/" />
    <updated>2026-04-02T00:00:00+00:00</updated>
    <title>Stickied AutoModerator post</title>
    <author><name>/u/AutoModerator</name></author>
    <content type="html">pinned content</content>
  </entry>
  <entry>
    <id>t3_post_b</id>
    <link href="https://www.reddit.com/r/MachineLearning/comments/post_b/b/" />
    <updated>2026-04-22T10:00:00+00:00</updated>
    <title>Recent post B</title>
    <author><name>/u/alice</name></author>
    <content type="html">b</content>
  </entry>
  <entry>
    <id>t3_post_c</id>
    <link href="https://www.reddit.com/r/MachineLearning/comments/post_c/c/" />
    <updated>2026-04-22T12:00:00+00:00</updated>
    <title>Recent post C</title>
    <author><name>/u/bob</name></author>
    <content type="html">c</content>
  </entry>
</feed>
"""


@pytest.mark.asyncio
async def test_fetch_does_not_break_on_checkpoint_match(monkeypatch):
    """Regression: Reddit /hot.rss pins stickied posts at the top. Breaking on
    a checkpoint match at position 0 used to drop every entry below. The
    adapter must return all entries and defer de-dup to the ingestion layer.
    """
    adapter = RSSAdapter("https://www.reddit.com/r/MachineLearning/hot.rss")

    async def fake_curl_fetch(url: str, headers: dict[str, str]) -> str:
        return MULTI_ENTRY_ATOM

    monkeypatch.setattr("app.adapters.rss._get_text_with_curl", fake_curl_fetch)

    # Checkpoint is the stickied post — a new sync must NOT stop at index 0.
    items, checkpoint = await adapter.fetch("t3_sticky_old")

    assert checkpoint == "t3_sticky_old"
    assert [item.source_item_id for item in items] == [
        "t3_sticky_old",
        "t3_post_b",
        "t3_post_c",
    ]
