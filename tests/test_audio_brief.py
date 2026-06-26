"""Unit tests for audio_brief.build_source_text — the only non-glue logic."""

import pytest

from ainews.audio_brief import build_source_text
from ainews.models import ContentItem


def _item(**kw) -> ContentItem:
    base = dict(
        id="x",
        url="https://example.com/a",
        title="Big Model Ships",
        source_name="OpenAI",
        source_type="rss",
        score=0.9,
        score_reason="Frontier model release",
    )
    base.update(kw)
    return ContentItem(**base)


def test_renders_core_fields():
    text = build_source_text([_item()])
    assert "Big Model Ships" in text
    assert "https://example.com/a" in text
    assert "OpenAI" in text
    assert "Frontier model release" in text
    assert "0.9" in text


def test_preserves_order():
    items = [
        _item(title="First", url="https://e.com/1"),
        _item(title="Second", url="https://e.com/2"),
    ]
    text = build_source_text(items)
    assert text.index("First") < text.index("Second")


def test_empty_list_raises():
    # Fail fast: generating a brief from nothing is a caller bug, not an empty doc.
    with pytest.raises(ValueError):
        build_source_text([])


def test_missing_score_does_not_crash():
    text = build_source_text([_item(score=None, score_reason="")])
    assert "Big Model Ships" in text
