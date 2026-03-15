"""Tests for core data models — make_id() determinism and user scoping."""

import pytest
from pydantic import ValidationError

from ainews.models import ContentItem, ScoredItem, make_id

# --- make_id ---


def test_make_id_deterministic():
    """Same URL always produces same ID."""
    url = "https://example.com/article"
    assert make_id(url) == make_id(url)


def test_make_id_different_urls():
    """Different URLs produce different IDs."""
    assert make_id("https://a.com") != make_id("https://b.com")


def test_make_id_length():
    """IDs are 16 hex characters."""
    result = make_id("https://example.com")
    assert len(result) == 16
    assert all(c in "0123456789abcdef" for c in result)


def test_make_id_user_scoped():
    """Same URL with different user_ids produces different IDs."""
    url = "https://example.com/article"
    id_user_a = make_id(url, user_id="user-a")
    id_user_b = make_id(url, user_id="user-b")
    id_no_user = make_id(url)
    assert id_user_a != id_user_b
    assert id_user_a != id_no_user


def test_make_id_user_none_same_as_no_user():
    """user_id=None behaves the same as omitting it."""
    url = "https://example.com/article"
    assert make_id(url) == make_id(url, user_id=None)


def test_make_id_empty_url():
    """Empty URL still produces a valid ID."""
    result = make_id("")
    assert len(result) == 16


def test_make_id_empty_user_id_treated_as_none():
    """Empty string user_id is falsy, so it behaves like None."""
    url = "https://example.com"
    assert make_id(url, user_id="") == make_id(url, user_id=None)


# --- ScoredItem validation ---


def test_scored_item_rejects_score_above_1():
    with pytest.raises(ValidationError):
        ScoredItem(relevance_score=1.5, tier="work", reason="test")


def test_scored_item_rejects_score_below_0():
    with pytest.raises(ValidationError):
        ScoredItem(relevance_score=-0.1, tier="work", reason="test")


def test_scored_item_accepts_boundary_scores():
    item_zero = ScoredItem(relevance_score=0, tier="personal", reason="noise")
    item_one = ScoredItem(relevance_score=1, tier="work", reason="critical")
    assert item_zero.relevance_score == 0
    assert item_one.relevance_score == 1


# --- ContentItem defaults ---


def test_content_item_defaults():
    item = ContentItem(
        id="abc123",
        url="https://example.com",
        title="Test",
        source_name="test",
        source_type="rss",
    )
    assert item.tags == []
    assert item.score is None
    assert item.is_duplicate_of is None
    assert item.summary == ""
