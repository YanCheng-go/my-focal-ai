"""Tests for source exploration — prompt building, response parsing, and dedup."""

from ainews.explore import (
    _build_existing_set,
    _build_explore_prompt,
    _summarize_existing_sources,
)

SAMPLE_CONFIG = {
    "sources": {
        "twitter": [
            {"handle": "karpathy", "tags": ["ai", "research"]},
            {"handle": "simonw", "tags": ["ai", "tooling"]},
        ],
        "youtube": [
            {"channel_id": "UCXUPKJO5MZQN11PqgIvyuvQ", "name": "Andrej Karpathy", "tags": ["ai"]},
        ],
        "rss": [
            {"url": "https://openai.com/news/rss.xml", "name": "OpenAI Blog", "tags": ["ai"]},
        ],
    }
}


# --- _summarize_existing_sources ---


def test_summarize_includes_twitter_handles():
    result = _summarize_existing_sources(SAMPLE_CONFIG)
    assert "karpathy" in result
    assert "simonw" in result


def test_summarize_includes_youtube_names():
    result = _summarize_existing_sources(SAMPLE_CONFIG)
    assert "Andrej Karpathy" in result


def test_summarize_includes_rss_names():
    result = _summarize_existing_sources(SAMPLE_CONFIG)
    assert "OpenAI Blog" in result


def test_summarize_includes_tags():
    result = _summarize_existing_sources(SAMPLE_CONFIG)
    assert "ai" in result
    assert "research" in result


def test_summarize_handles_empty_sources():
    result = _summarize_existing_sources({"sources": {}})
    assert result == ""


def test_summarize_handles_none_entries():
    config = {"sources": {"twitter": None, "rss": []}}
    result = _summarize_existing_sources(config)
    assert result == ""


# --- _build_existing_set ---


def test_existing_set_includes_handles():
    existing = _build_existing_set(SAMPLE_CONFIG)
    assert "karpathy" in existing
    assert "simonw" in existing


def test_existing_set_includes_channel_ids():
    existing = _build_existing_set(SAMPLE_CONFIG)
    assert "ucxupkjo5mzqn11pqgivyuvq" in existing


def test_existing_set_includes_urls():
    existing = _build_existing_set(SAMPLE_CONFIG)
    assert "https://openai.com/news/rss.xml" in existing


def test_existing_set_includes_names():
    existing = _build_existing_set(SAMPLE_CONFIG)
    assert "openai blog" in existing
    assert "andrej karpathy" in existing


def test_existing_set_empty_config():
    existing = _build_existing_set({"sources": {}})
    assert len(existing) == 0


# --- _build_explore_prompt ---


def test_explore_prompt_includes_sources():
    prompt = _build_explore_prompt(SAMPLE_CONFIG)
    assert "karpathy" in prompt
    assert "OpenAI Blog" in prompt


def test_explore_prompt_type_filter():
    prompt = _build_explore_prompt(SAMPLE_CONFIG, source_type="twitter")
    assert "twitter" in prompt.lower()


def test_explore_prompt_limit():
    prompt = _build_explore_prompt(SAMPLE_CONFIG, limit=5)
    assert "5" in prompt


def test_explore_prompt_no_filter():
    prompt = _build_explore_prompt(SAMPLE_CONFIG)
    assert "Only suggest" not in prompt


# --- Response parsing (unit test the filtering logic) ---


def test_dedup_filters_existing_handles():
    existing = _build_existing_set(SAMPLE_CONFIG)
    suggestion = {"config": {"handle": "karpathy"}, "name": "Karpathy"}
    identifiers = [
        suggestion["config"].get("handle", ""),
        suggestion.get("name", ""),
    ]
    assert any(ident.lower() in existing for ident in identifiers if ident)


def test_dedup_allows_new_handles():
    existing = _build_existing_set(SAMPLE_CONFIG)
    suggestion = {"config": {"handle": "ylecun"}, "name": "Yann LeCun"}
    identifiers = [
        suggestion["config"].get("handle", ""),
        suggestion.get("name", ""),
    ]
    assert not any(ident.lower() in existing for ident in identifiers if ident)


def test_dedup_case_insensitive():
    existing = _build_existing_set(SAMPLE_CONFIG)
    assert "karpathy" in existing
    # The set stores lowercase, so uppercase handle should still match
    assert "Karpathy".lower() in existing
