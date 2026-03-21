"""Tests for source exploration validation layer."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from ainews.explore_validate import (
    _check_rss,
    _check_twitter,
    _check_youtube,
    validate_suggestion,
    validate_suggestions,
)


def _mock_response(status_code=200, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


# --- _check_youtube ---


def test_youtube_valid_channel_id():
    """Valid channel ID format + 200 response = verified."""
    client = AsyncMock()
    client.head = AsyncMock(return_value=_mock_response(200))
    result = asyncio.run(
        _check_youtube({"channel_id": "UCXUPKJO5MZQN11PqgIvyuvQ"}, client)
    )
    assert result is True


def test_youtube_invalid_channel_id_format():
    """Invalid channel_id format (not UC + 22 chars)."""
    client = AsyncMock()
    result = asyncio.run(_check_youtube({"channel_id": "invalid"}, client))
    assert result is False


def test_youtube_missing_channel_id():
    client = AsyncMock()
    result = asyncio.run(_check_youtube({}, client))
    assert result is False


def test_youtube_404_response():
    """Channel ID has correct format but channel doesn't exist."""
    client = AsyncMock()
    client.head = AsyncMock(return_value=_mock_response(404))
    result = asyncio.run(
        _check_youtube({"channel_id": "UCxxxxxxxxxxxxxxxxxxxxxxx"}, client)
    )
    assert result is False


# --- _check_twitter ---


def test_twitter_valid_handle():
    client = AsyncMock()
    client.head = AsyncMock(return_value=_mock_response(200))
    result = asyncio.run(_check_twitter({"handle": "karpathy"}, client))
    assert result is True


def test_twitter_invalid_handle_format():
    """Handle with special chars should fail format check."""
    client = AsyncMock()
    result = asyncio.run(
        _check_twitter({"handle": "not a handle!"}, client)
    )
    assert result is False


def test_twitter_handle_too_long():
    client = AsyncMock()
    result = asyncio.run(_check_twitter({"handle": "a" * 16}, client))
    assert result is False


def test_twitter_404_handle():
    client = AsyncMock()
    client.head = AsyncMock(return_value=_mock_response(404))
    result = asyncio.run(
        _check_twitter({"handle": "zzz_fake_zzz"}, client)
    )
    assert result is False


def test_twitter_missing_handle():
    client = AsyncMock()
    result = asyncio.run(_check_twitter({}, client))
    assert result is False


# --- _check_rss ---


def test_rss_valid_feed():
    client = AsyncMock()
    client.get = AsyncMock(
        return_value=_mock_response(200, '<?xml version="1.0"?><rss></rss>')
    )
    result = asyncio.run(
        _check_rss({"url": "https://example.com/feed.xml"}, client)
    )
    assert result is True


def test_rss_not_xml():
    """URL returns 200 but content is HTML, not RSS."""
    client = AsyncMock()
    client.get = AsyncMock(
        return_value=_mock_response(
            200, "<html><body>Not a feed</body></html>"
        )
    )
    result = asyncio.run(
        _check_rss({"url": "https://example.com/page"}, client)
    )
    assert result is False


def test_rss_404():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_mock_response(404))
    result = asyncio.run(
        _check_rss({"url": "https://example.com/missing.xml"}, client)
    )
    assert result is False


def test_rss_missing_url():
    client = AsyncMock()
    result = asyncio.run(_check_rss({}, client))
    assert result is False


def test_rss_atom_feed():
    """Atom feeds should also validate."""
    client = AsyncMock()
    client.get = AsyncMock(
        return_value=_mock_response(
            200, '<feed xmlns="http://www.w3.org/2005/Atom">'
        )
    )
    result = asyncio.run(
        _check_rss({"url": "https://example.com/atom.xml"}, client)
    )
    assert result is True


# --- validate_suggestion ---


def test_validate_suggestion_verified():
    client = AsyncMock()
    client.head = AsyncMock(return_value=_mock_response(200))
    s = {
        "source_type": "youtube",
        "name": "Test",
        "config": {"channel_id": "UCXUPKJO5MZQN11PqgIvyuvQ"},
    }
    result = asyncio.run(validate_suggestion(s, client))
    assert result["verified"] is True


def test_validate_suggestion_unknown_type():
    """Unknown source types get verified=None (not filtered out)."""
    client = AsyncMock()
    s = {
        "source_type": "some_new_type",
        "name": "Test",
        "config": {},
    }
    result = asyncio.run(validate_suggestion(s, client))
    assert result["verified"] is None


def test_validate_suggestion_failed():
    client = AsyncMock()
    client.head = AsyncMock(return_value=_mock_response(404))
    s = {
        "source_type": "youtube",
        "name": "Fake",
        "config": {"channel_id": "UCxxxxxxxxxxxxxxxxxxxxxxx"},
    }
    result = asyncio.run(validate_suggestion(s, client))
    assert result["verified"] is False


# --- validate_suggestions (integration) ---


def test_validate_suggestions_filters_invalid():
    """Invalid suggestions should be removed from results."""
    suggestions = [
        {
            "source_type": "youtube",
            "name": "Real",
            "config": {"channel_id": "UCXUPKJO5MZQN11PqgIvyuvQ"},
            "relevance_score": 0.9,
            "reason": "good",
            "tags": [],
        },
        {
            "source_type": "youtube",
            "name": "Fake",
            "config": {"channel_id": "UCxxxxxxxxxxxxxxxxxxxxxxx"},
            "relevance_score": 0.8,
            "reason": "hallucinated",
            "tags": [],
        },
    ]

    async def _mock_head(url, **kwargs):
        if "UCXUPKJO5MZQN11PqgIvyuvQ" in url:
            return _mock_response(200)
        return _mock_response(404)

    with patch("ainews.explore_validate.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.head = AsyncMock(side_effect=_mock_head)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        result = asyncio.run(validate_suggestions(suggestions))

    assert len(result) == 1
    assert result[0]["name"] == "Real"
    assert result[0]["verified"] is True


def test_validate_suggestions_keeps_unknown_types():
    """Sources with no validator should be kept (verified=None)."""
    suggestions = [
        {
            "source_type": "luma",
            "name": "Some Event",
            "config": {"handle": "test"},
            "relevance_score": 0.7,
            "reason": "ok",
            "tags": [],
        },
    ]

    with patch("ainews.explore_validate.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        result = asyncio.run(validate_suggestions(suggestions))

    assert len(result) == 1
    assert result[0]["verified"] is None


def test_validate_suggestions_empty():
    result = asyncio.run(validate_suggestions([]))
    assert result == []
