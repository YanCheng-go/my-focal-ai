"""Tests for source exploration validation layer."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from ainews.explore_validate import (
    _check_rss,
    _check_rsshub,
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


# --- _check_rsshub ---


def test_rsshub_valid_route():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_mock_response(200))
    result = asyncio.run(
        _check_rsshub(
            {"route": "/twitter/user/test"},
            client,
            rsshub_base="http://localhost:1200",
        )
    )
    assert result is True


def test_rsshub_missing_route():
    client = AsyncMock()
    result = asyncio.run(
        _check_rsshub({}, client, rsshub_base="http://localhost:1200")
    )
    assert result is False


def test_rsshub_404():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_mock_response(404))
    result = asyncio.run(
        _check_rsshub(
            {"route": "/nonexistent/route"},
            client,
            rsshub_base="http://localhost:1200",
        )
    )
    assert result is False


def test_rsshub_prepends_slash():
    """Route without leading slash should still work."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=_mock_response(200))
    result = asyncio.run(
        _check_rsshub(
            {"route": "twitter/user/test"},
            client,
            rsshub_base="http://localhost:1200",
        )
    )
    assert result is True
    call_args = client.get.call_args
    assert call_args[0][0] == "http://localhost:1200/twitter/user/test"


# --- HTTP error handling ---


def test_youtube_network_error():
    """Network timeout should return False, not raise."""
    client = AsyncMock()
    client.head = AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))
    result = asyncio.run(
        _check_youtube({"channel_id": "UCXUPKJO5MZQN11PqgIvyuvQ"}, client)
    )
    assert result is False


def test_twitter_network_error():
    client = AsyncMock()
    client.head = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
    result = asyncio.run(
        _check_twitter({"handle": "karpathy"}, client)
    )
    assert result is False


def test_rss_network_error():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    result = asyncio.run(
        _check_rss({"url": "https://example.com/feed.xml"}, client)
    )
    assert result is False


# --- explore_sources end-to-end (mocked LLM) ---


def test_explore_sources_parses_llm_response():
    """explore_sources should parse LLM JSON, dedup, filter, and validate."""
    from ainews.explore import explore_sources

    llm_response = json.dumps([
        {
            "source_type": "twitter",
            "name": "Yann LeCun",
            "config": {"handle": "ylecun"},
            "tags": ["ai"],
            "relevance_score": 0.9,
            "reason": "AI researcher",
        },
        {
            "source_type": "twitter",
            "name": "karpathy",
            "config": {"handle": "karpathy"},
            "tags": ["ai"],
            "relevance_score": 0.8,
            "reason": "Already followed",
        },
    ])

    sample_config = {
        "sources": {
            "twitter": [{"handle": "karpathy", "tags": ["ai"]}],
        }
    }

    mock_ollama_resp = MagicMock()
    mock_ollama_resp.status_code = 200
    mock_ollama_resp.raise_for_status = MagicMock()
    mock_ollama_resp.json.return_value = {
        "message": {"content": llm_response}
    }

    with (
        patch("ainews.explore.httpx.AsyncClient") as mock_http,
        patch("ainews.explore.Settings") as mock_settings,
        patch("ainews.explore.load_sources", return_value=sample_config),
        patch("ainews.explore.load_principles", return_value=SAMPLE_PRINCIPLES),
        patch("ainews.explore.validate_suggestions", new=_passthrough_validate),
    ):
        mock_settings.return_value.config_dir = "/tmp"
        mock_settings.return_value.ollama_base_url = "http://localhost:11434"
        mock_settings.return_value.ollama_model = "qwen3:4b"
        mock_settings.return_value.rsshub_base = "http://localhost:1200"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_ollama_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value = mock_client

        results = asyncio.run(explore_sources(
            sources_config=sample_config,
            ollama_base_url="http://localhost:11434",
            model="qwen3:4b",
        ))

    # karpathy should be deduped out
    assert len(results) == 1
    assert results[0]["name"] == "Yann LeCun"
    assert results[0]["config"]["handle"] == "ylecun"


def test_explore_sources_handles_wrapped_json():
    """LLM sometimes returns {"suggestions": [...]} instead of bare array."""
    from ainews.explore import explore_sources

    llm_response = json.dumps({
        "suggestions": [
            {
                "source_type": "rss",
                "name": "Some Blog",
                "config": {"url": "https://example.com/feed.xml"},
                "tags": ["tech"],
                "relevance_score": 0.7,
                "reason": "Tech blog",
            }
        ]
    })

    mock_ollama_resp = MagicMock()
    mock_ollama_resp.status_code = 200
    mock_ollama_resp.raise_for_status = MagicMock()
    mock_ollama_resp.json.return_value = {
        "message": {"content": llm_response}
    }

    with (
        patch("ainews.explore.httpx.AsyncClient") as mock_http,
        patch("ainews.explore.Settings") as mock_settings,
        patch("ainews.explore.load_sources"),
        patch("ainews.explore.load_principles", return_value=SAMPLE_PRINCIPLES),
        patch("ainews.explore.validate_suggestions", new=_passthrough_validate),
    ):
        mock_settings.return_value.config_dir = "/tmp"
        mock_settings.return_value.ollama_base_url = "http://localhost:11434"
        mock_settings.return_value.ollama_model = "qwen3:4b"
        mock_settings.return_value.rsshub_base = "http://localhost:1200"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_ollama_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value = mock_client

        results = asyncio.run(explore_sources(
            sources_config={"sources": {}},
            ollama_base_url="http://localhost:11434",
            model="qwen3:4b",
        ))

    assert len(results) == 1
    assert results[0]["name"] == "Some Blog"


def test_explore_sources_handles_invalid_json():
    """Malformed LLM output should return empty list, not crash."""
    from ainews.explore import explore_sources

    mock_ollama_resp = MagicMock()
    mock_ollama_resp.status_code = 200
    mock_ollama_resp.raise_for_status = MagicMock()
    mock_ollama_resp.json.return_value = {
        "message": {"content": "not valid json at all"}
    }

    with (
        patch("ainews.explore.httpx.AsyncClient") as mock_http,
        patch("ainews.explore.Settings") as mock_settings,
        patch("ainews.explore.load_sources"),
        patch("ainews.explore.load_principles", return_value=SAMPLE_PRINCIPLES),
    ):
        mock_settings.return_value.config_dir = "/tmp"
        mock_settings.return_value.ollama_base_url = "http://localhost:11434"
        mock_settings.return_value.ollama_model = "qwen3:4b"
        mock_settings.return_value.rsshub_base = "http://localhost:1200"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_ollama_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value = mock_client

        results = asyncio.run(explore_sources(
            sources_config={"sources": {}},
            ollama_base_url="http://localhost:11434",
            model="qwen3:4b",
        ))

    assert results == []


def test_explore_sources_filters_by_min_score():
    """Suggestions below min_score should be excluded."""
    from ainews.explore import explore_sources

    llm_response = json.dumps([
        {
            "source_type": "twitter",
            "name": "High Score",
            "config": {"handle": "highscore"},
            "tags": [],
            "relevance_score": 0.9,
            "reason": "Great",
        },
        {
            "source_type": "twitter",
            "name": "Low Score",
            "config": {"handle": "lowscore"},
            "tags": [],
            "relevance_score": 0.2,
            "reason": "Meh",
        },
    ])

    mock_ollama_resp = MagicMock()
    mock_ollama_resp.status_code = 200
    mock_ollama_resp.raise_for_status = MagicMock()
    mock_ollama_resp.json.return_value = {
        "message": {"content": llm_response}
    }

    with (
        patch("ainews.explore.httpx.AsyncClient") as mock_http,
        patch("ainews.explore.Settings") as mock_settings,
        patch("ainews.explore.load_sources"),
        patch("ainews.explore.load_principles", return_value=SAMPLE_PRINCIPLES),
        patch("ainews.explore.validate_suggestions", new=_passthrough_validate),
    ):
        mock_settings.return_value.config_dir = "/tmp"
        mock_settings.return_value.ollama_base_url = "http://localhost:11434"
        mock_settings.return_value.ollama_model = "qwen3:4b"
        mock_settings.return_value.rsshub_base = "http://localhost:1200"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_ollama_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_http.return_value = mock_client

        results = asyncio.run(explore_sources(
            sources_config={"sources": {}},
            ollama_base_url="http://localhost:11434",
            model="qwen3:4b",
            min_score=0.5,
        ))

    assert len(results) == 1
    assert results[0]["name"] == "High Score"


# --- Helpers for e2e tests ---

SAMPLE_PRINCIPLES = {
    "topic": "AI and technology",
    "principles": {
        "signal_over_noise": {
            "name": "Signal over Noise",
            "description": "Prefer verifiable signal",
        },
    },
    "source_proximity": {},
}


async def _passthrough_validate(suggestions, **kwargs):
    """Skip real HTTP validation in e2e tests."""
    for s in suggestions:
        s["verified"] = True
    return suggestions
