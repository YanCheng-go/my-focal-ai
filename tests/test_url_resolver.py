"""Tests for URL resolver — source field extraction from URLs."""

import asyncio
from urllib.parse import urlparse

import pytest

from ainews.sources.url_constants import resolve_olshansk, resolve_rsshub_for_url
from ainews.sources.url_resolver import resolve_url


def _run(coro):
    return asyncio.run(coro)


# --- Twitter/X (no network) ---


def test_twitter_url():
    result = _run(resolve_url("https://x.com/karpathy"))
    assert result.source_type == "twitter"
    assert result.fields == {"handle": "karpathy"}


def test_twitter_url_with_at():
    result = _run(resolve_url("https://x.com/@karpathy"))
    assert result.source_type == "twitter"
    assert result.fields["handle"] == "karpathy"


def test_twitter_status_url():
    result = _run(resolve_url("https://x.com/karpathy/status/123456"))
    assert result.source_type == "twitter"
    assert result.fields["handle"] == "karpathy"


def test_twitter_old_domain():
    result = _run(resolve_url("https://twitter.com/elonmusk"))
    assert result.source_type == "twitter"
    assert result.fields["handle"] == "elonmusk"


def test_twitter_rejects_non_profile():
    with pytest.raises(ValueError, match="Could not extract handle"):
        _run(resolve_url("https://x.com/home"))


def test_twitter_rejects_settings():
    with pytest.raises(ValueError, match="Could not extract handle"):
        _run(resolve_url("https://x.com/settings"))


# --- arXiv (no network) ---


def test_arxiv_paper_url():
    result = _run(resolve_url("https://arxiv.org/abs/2405.12345"))
    assert result.source_type == "arxiv"
    assert "id:2405.12345" in result.fields["url"]
    assert result.fields["name"] == "arXiv:2405.12345"
    assert "research" in result.suggested_tags


def test_arxiv_pdf_url():
    result = _run(resolve_url("https://arxiv.org/pdf/2405.12345"))
    assert result.source_type == "arxiv"
    assert "id:2405.12345" in result.fields["url"]


def test_arxiv_category_url():
    result = _run(resolve_url("https://arxiv.org/list/cs.AI/recent"))
    assert result.source_type == "arxiv"
    assert "rss.arxiv.org/rss/cs.AI" in result.fields["url"]
    assert result.fields["name"] == "arXiv:cs.AI"


def test_arxiv_invalid_url():
    with pytest.raises(ValueError, match="Could not parse arXiv"):
        _run(resolve_url("https://arxiv.org/"))


# --- Xiaohongshu → RSSHub (no network) ---


def test_xiaohongshu_profile():
    result = _run(resolve_url("https://xiaohongshu.com/user/profile/5a1234bc"))
    assert result.source_type == "rsshub"
    assert result.fields["route"] == "/xiaohongshu/user/5a1234bc/notes"
    assert "XHS:" in result.fields["name"]


def test_xiaohongshu_invalid():
    with pytest.raises(ValueError, match="Could not parse Xiaohongshu"):
        _run(resolve_url("https://xiaohongshu.com/explore"))


# --- Luma (no network) ---


def test_luma_url():
    result = _run(resolve_url("https://lu.ma/ai-meetup"))
    assert result.source_type == "luma"
    assert result.fields["handle"] == "ai-meetup"


def test_luma_empty():
    with pytest.raises(ValueError, match="Could not extract.*Luma"):
        _run(resolve_url("https://lu.ma/"))


# --- RSSHub (no network) ---


def test_rsshub_url():
    result = _run(resolve_url("https://rsshub.app/twitter/user/karpathy"))
    assert result.source_type == "rsshub"
    assert result.fields["route"] == "twitter/user/karpathy"
    assert "RSSHub:" in result.fields["name"]


def test_rsshub_empty_route():
    with pytest.raises(ValueError, match="Empty RSSHub route"):
        _run(resolve_url("https://rsshub.app/"))


# --- URL normalization ---


def test_url_without_scheme():
    result = _run(resolve_url("x.com/karpathy"))
    assert result.source_type == "twitter"
    assert result.fields["handle"] == "karpathy"


# --- RSSHub URL map resolution (no network, mocked maps) ---


_MOCK_RSSHUB_MAP = {
    "www.example.com/news": "/example/news",
    "techcrunch.com": "/techcrunch/news",
    "overlap.com": "/overlap/feed",
}

_MOCK_OLSHANSK_MAP = {
    "cursor.com/blog": {"url": "https://feeds.example.com/cursor.xml", "name": "Cursor Blog"},
    "overlap.com": {"url": "https://feeds.example.com/overlap.xml", "name": "Overlap Site"},
}


def test_rsshub_for_url_known_site(monkeypatch):
    monkeypatch.setattr("ainews.sources.url_constants.RSSHUB_URL_MAP", _MOCK_RSSHUB_MAP)
    parsed = urlparse("https://www.example.com/news")
    result = resolve_rsshub_for_url(parsed)
    assert result is not None
    assert result["source_type"] == "rsshub"
    assert result["fields"]["route"] == "/example/news"


def test_rsshub_for_url_without_www(monkeypatch):
    monkeypatch.setattr("ainews.sources.url_constants.RSSHUB_URL_MAP", _MOCK_RSSHUB_MAP)
    parsed = urlparse("https://techcrunch.com")
    result = resolve_rsshub_for_url(parsed)
    assert result is not None
    assert result["fields"]["route"] == "/techcrunch/news"


def test_rsshub_for_url_unknown_returns_none(monkeypatch):
    monkeypatch.setattr("ainews.sources.url_constants.RSSHUB_URL_MAP", _MOCK_RSSHUB_MAP)
    parsed = urlparse("https://totally-unknown-site.example.com/page")
    assert resolve_rsshub_for_url(parsed) is None


# --- Olshansk feed map resolution (no network, mocked maps) ---


def test_olshansk_known_site(monkeypatch):
    monkeypatch.setattr("ainews.sources.url_constants.OLSHANSK_FEED_MAP", _MOCK_OLSHANSK_MAP)
    parsed = urlparse("https://cursor.com/blog")
    result = resolve_olshansk(parsed)
    assert result is not None
    assert result["source_type"] == "rss"
    assert result["fields"]["url"] == "https://feeds.example.com/cursor.xml"
    assert result["fields"]["name"] == "Cursor Blog"


def test_olshansk_unknown_returns_none(monkeypatch):
    monkeypatch.setattr("ainews.sources.url_constants.OLSHANSK_FEED_MAP", _MOCK_OLSHANSK_MAP)
    parsed = urlparse("https://totally-unknown-site.example.com")
    assert resolve_olshansk(parsed) is None


def test_rsshub_preferred_over_olshansk(monkeypatch):
    """When both maps match the same key, RSSHub wins (checked first in resolver)."""
    monkeypatch.setattr("ainews.sources.url_constants.RSSHUB_URL_MAP", _MOCK_RSSHUB_MAP)
    monkeypatch.setattr("ainews.sources.url_constants.OLSHANSK_FEED_MAP", _MOCK_OLSHANSK_MAP)
    result = _run(resolve_url("https://overlap.com"))
    assert result.source_type == "rsshub"
    assert result.fields["route"] == "/overlap/feed"
