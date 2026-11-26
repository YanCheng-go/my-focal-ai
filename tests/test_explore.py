"""Tests for source exploration — prompt building, response parsing, and dedup."""

from ainews.explore import (
    _build_existing_set,
    _build_explore_prompt,
    _format_principles,
    _format_proximity,
    _summarize_existing_sources,
    build_system_prompt,
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

SAMPLE_PRINCIPLES = {
    "topic": "AI and technology",
    "principles": {
        "signal_over_noise": {
            "name": "Signal over Noise (Shannon)",
            "description": "Prefer sources that produce verifiable signal",
            "indicators": {
                "signal": ["Contains reproducible results", "References specific methods"],
                "noise": ["Vague claims without specifics"],
            },
        },
        "mechanism_over_opinion": {
            "name": "Mechanisms over Opinions (First Principles)",
            "description": "Prefer explanations of how/why things work",
            "indicators": {
                "mechanism": ["Explains WHY a model works"],
                "opinion": ["Makes claims without explanation"],
            },
        },
        "builders_over_commentators": {
            "name": "Builders over Commentators (Skin in the Game)",
            "description": "Prefer people who build things",
            "source_trust": {
                "high": ["ML engineers, researchers publishing code"],
                "low": ["AI influencers and hype commentators"],
            },
        },
    },
    "source_proximity": {
        "tier_1_origin": ["Research papers", "Open research and code"],
        "tier_2_implementation": ["Engineering blogs", "Technical tutorials"],
        "tier_3_derivative": ["News coverage of research"],
        "tier_4_noise": ["Hype amplification"],
    },
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


# --- _format_principles ---


def test_format_principles_includes_all_three():
    result = _format_principles(SAMPLE_PRINCIPLES)
    assert "Signal over Noise" in result
    assert "Mechanisms over Opinions" in result
    assert "Builders over Commentators" in result


def test_format_principles_includes_descriptions():
    result = _format_principles(SAMPLE_PRINCIPLES)
    assert "verifiable signal" in result
    assert "how/why things work" in result


def test_format_principles_includes_indicators():
    result = _format_principles(SAMPLE_PRINCIPLES)
    assert "reproducible results" in result
    assert "Vague claims" in result


def test_format_principles_includes_source_trust():
    result = _format_principles(SAMPLE_PRINCIPLES)
    assert "ML engineers" in result
    assert "hype commentators" in result


def test_format_principles_empty():
    result = _format_principles({})
    assert result == ""


# --- _format_proximity ---


def test_format_proximity_includes_tiers():
    result = _format_proximity(SAMPLE_PRINCIPLES)
    assert "Tier 1 Origin" in result
    assert "Tier 4 Noise" in result


def test_format_proximity_includes_examples():
    result = _format_proximity(SAMPLE_PRINCIPLES)
    assert "Research papers" in result
    assert "Hype amplification" in result


def test_format_proximity_empty():
    result = _format_proximity({})
    assert result == ""


# --- build_system_prompt ---


def test_system_prompt_includes_principles():
    prompt = build_system_prompt(SAMPLE_PRINCIPLES)
    assert "Signal over Noise" in prompt
    assert "Builders over Commentators" in prompt


def test_system_prompt_includes_proximity():
    prompt = build_system_prompt(SAMPLE_PRINCIPLES)
    assert "Tier 1 Origin" in prompt


def test_system_prompt_includes_scoring_instruction():
    prompt = build_system_prompt(SAMPLE_PRINCIPLES)
    assert "relevance_score" in prompt
    assert "principles" in prompt.lower()


# --- _build_explore_prompt ---


def test_explore_prompt_includes_sources():
    prompt = _build_explore_prompt(SAMPLE_CONFIG, SAMPLE_PRINCIPLES)
    assert "karpathy" in prompt
    assert "OpenAI Blog" in prompt


def test_explore_prompt_includes_topic():
    prompt = _build_explore_prompt(SAMPLE_CONFIG, SAMPLE_PRINCIPLES)
    assert "AI and technology" in prompt


def test_explore_prompt_type_filter():
    prompt = _build_explore_prompt(
        SAMPLE_CONFIG, SAMPLE_PRINCIPLES, source_type="twitter"
    )
    assert "twitter" in prompt.lower()


def test_explore_prompt_limit():
    prompt = _build_explore_prompt(
        SAMPLE_CONFIG, SAMPLE_PRINCIPLES, limit=5
    )
    assert "5" in prompt


def test_explore_prompt_no_filter():
    prompt = _build_explore_prompt(SAMPLE_CONFIG, SAMPLE_PRINCIPLES)
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
