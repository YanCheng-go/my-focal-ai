"""Tests for scorer — prompt building, response parsing, and fallback."""

import json

from ainews.models import ContentItem, ScoredItem
from ainews.scoring.scorer import _apply_score, _build_user_prompt


def _item(**kwargs):
    defaults = dict(
        id="test1",
        url="https://example.com",
        title="Test Title",
        source_name="TestSource",
        source_type="rss",
    )
    defaults.update(kwargs)
    return ContentItem(**defaults)


# --- _build_user_prompt ---


def test_prompt_includes_title():
    item = _item(title="New Transformer Paper")
    prompt = _build_user_prompt(item, {})
    assert "New Transformer Paper" in prompt


def test_prompt_includes_source_info():
    item = _item(source_name="ArXiv", source_type="rss")
    prompt = _build_user_prompt(item, {})
    assert "ArXiv" in prompt
    assert "rss" in prompt


def test_prompt_uses_content_first():
    item = _item(content="Full article text here", summary="Short summary")
    prompt = _build_user_prompt(item, {})
    assert "Full article text here" in prompt


def test_prompt_falls_back_to_summary():
    item = _item(content="", summary="Short summary")
    prompt = _build_user_prompt(item, {})
    assert "Short summary" in prompt


def test_prompt_falls_back_to_title():
    item = _item(content="", summary="")
    prompt = _build_user_prompt(item, {})
    assert "Test Title" in prompt


def test_prompt_truncates_long_content():
    item = _item(content="x" * 3000)
    prompt = _build_user_prompt(item, {})
    assert "..." in prompt
    # The 2000-char truncation + "..." should be in the prompt
    assert "x" * 2001 not in prompt


# --- Response parsing (ScoredItem from LLM output) ---


def test_parse_valid_response():
    raw = '{"relevance_score": 0.8, "tier": "work", "reason": "good signal"}'
    parsed = json.loads(raw)
    scored = ScoredItem(**parsed)
    assert scored.relevance_score == 0.8
    assert scored.tier == "work"


def test_parse_response_with_all_fields():
    raw = {
        "relevance_score": 0.9,
        "tier": "work",
        "reason": "Original research with code",
        "key_topics": ["transformers", "efficiency"],
        "source_proximity": "origin",
    }
    scored = ScoredItem(**raw)
    assert scored.key_topics == ["transformers", "efficiency"]
    assert scored.source_proximity == "origin"


def test_parse_response_defaults_optional_fields():
    raw = {"relevance_score": 0.5, "reason": "ok"}
    scored = ScoredItem(**raw)
    assert scored.tier == "personal"
    assert scored.key_topics == []
    assert scored.source_proximity == "derivative"


def test_parse_malformed_json_triggers_fallback():
    """Simulate the fallback path in score_item when JSON parsing fails."""
    content = "This is not JSON at all"
    try:
        parsed = json.loads(content)
        ScoredItem(**parsed)
        raise AssertionError("Should have raised")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        scored = ScoredItem(
            relevance_score=0.5,
            tier="personal",
            reason="Scoring failed — defaulting to neutral",
            key_topics=[],
        )
    assert scored.relevance_score == 0.5
    assert scored.tier == "personal"


def test_parse_markdown_fenced_json_triggers_fallback():
    """LLMs sometimes wrap JSON in ```json fences — json.loads rejects this."""
    content = '```json\n{"relevance_score": 0.8, "tier": "work", "reason": "good"}\n```'
    try:
        parsed = json.loads(content)
        ScoredItem(**parsed)
        raise AssertionError("Should have raised")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        scored = ScoredItem(
            relevance_score=0.5,
            tier="personal",
            reason="Scoring failed — defaulting to neutral",
            key_topics=[],
        )
    assert scored.relevance_score == 0.5


def test_parse_extra_fields_ignored():
    """LLMs may return extra fields not in the schema — Pydantic ignores them."""
    raw = {
        "relevance_score": 0.7,
        "tier": "work",
        "reason": "solid",
        "unexpected_field": "should be ignored",
    }
    scored = ScoredItem(**raw)
    assert scored.relevance_score == 0.7
    assert not hasattr(scored, "unexpected_field")


# --- _apply_score ---


def test_apply_score_sets_fields():
    item = _item()
    scored = ScoredItem(relevance_score=0.9, tier="work", reason="great signal")
    _apply_score(item, scored)
    assert item.score == 0.9
    assert item.score_reason == "great signal"
    assert item.tier == "work"


def test_apply_score_returns_tuple():
    item = _item()
    scored = ScoredItem(relevance_score=0.5, tier="personal", reason="ok")
    result = _apply_score(item, scored)
    assert result == (item, scored)
