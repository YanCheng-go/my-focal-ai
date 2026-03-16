"""Tests for backfill — tag/source_type sync from config to DB."""

from ainews.backfill import _apply_metadata_updates, _build_source_map

# --- _build_source_map ---


def _make_config(**source_sections) -> dict:
    """Helper to build a sources_config dict."""
    return {"rsshub_base": "http://localhost:1200", "sources": source_sections}


def test_build_source_map_empty():
    result = _build_source_map({"sources": {}})
    assert result == {}


def test_build_source_map_twitter():
    config = _make_config(twitter=[{"handle": "karpathy", "tags": ["ai"]}])
    result = _build_source_map(config)
    assert "@karpathy" in result
    assert result["@karpathy"]["tags"] == ["ai"]
    assert result["@karpathy"]["source_type"] == "twitter"


def test_build_source_map_events():
    config = _make_config(events=[{"name": "Anthropic Events", "tags": ["events", "ai"]}])
    result = _build_source_map(config)
    assert "Anthropic Events" in result
    assert result["Anthropic Events"]["source_type"] == "events"


def test_build_source_map_rss():
    config = _make_config(
        rss=[{"url": "https://blog.example.com/feed", "name": "Example Blog", "tags": ["tech"]}]
    )
    result = _build_source_map(config)
    assert "Example Blog" in result
    assert result["Example Blog"]["source_type"] == "rss"


def test_build_source_map_youtube():
    config = _make_config(
        youtube=[{"channel_id": "UC123", "name": "AI Channel", "tags": ["youtube"]}]
    )
    result = _build_source_map(config)
    assert "AI Channel" in result
    assert result["AI Channel"]["source_type"] == "youtube"


def test_build_source_map_xiaohongshu_via_rsshub():
    """XHS sources are now RSSHub routes with source_type=xiaohongshu."""
    config = _make_config(
        rsshub=[
            {
                "route": "/xiaohongshu/user/abc123/notes",
                "name": "XHS User",
                "source_type": "xiaohongshu",
                "tags": ["china"],
            }
        ]
    )
    result = _build_source_map(config)
    assert "XHS User" in result
    assert result["XHS User"]["source_type"] == "xiaohongshu"
    assert result["XHS User"]["tags"] == ["china"]


def test_build_source_map_luma():
    config = _make_config(luma=[{"handle": "ai-meetup", "tags": ["events"]}])
    result = _build_source_map(config)
    assert "Luma: ai-meetup" in result
    assert result["Luma: ai-meetup"]["source_type"] == "luma"


def test_build_source_map_multiple_types():
    config = _make_config(
        twitter=[{"handle": "alice", "tags": ["ai"]}],
        events=[{"name": "Google Events", "tags": ["events"]}],
        rss=[{"url": "https://blog.example.com/feed", "name": "Blog", "tags": []}],
    )
    result = _build_source_map(config)
    assert len(result) == 3
    assert "@alice" in result
    assert "Google Events" in result
    assert "Blog" in result


# --- _apply_metadata_updates ---


class FakeBackend:
    """Minimal backend stub for backfill tests."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.updates: list[tuple] = []

    def get_items_for_backfill(self):
        return self._rows

    def update_item_metadata(self, item_id, tags, source_type):
        self.updates.append((item_id, tags, source_type))


def test_apply_no_changes_needed():
    rows = [{"id": "1", "source_name": "@alice", "source_type": "twitter", "tags": '["ai"]'}]
    source_map = {"@alice": {"tags": ["ai"], "source_type": "twitter"}}
    backend = FakeBackend(rows)
    updated = _apply_metadata_updates(backend, source_map)
    assert updated == 0
    assert backend.updates == []


def test_apply_tags_changed():
    rows = [{"id": "1", "source_name": "@alice", "source_type": "twitter", "tags": '["old"]'}]
    source_map = {"@alice": {"tags": ["new"], "source_type": "twitter"}}
    backend = FakeBackend(rows)
    updated = _apply_metadata_updates(backend, source_map)
    assert updated == 1
    assert backend.updates == [("1", ["new"], "twitter")]


def test_apply_type_changed():
    rows = [{"id": "1", "source_name": "Blog", "source_type": "rss", "tags": "[]"}]
    source_map = {"Blog": {"tags": [], "source_type": "feed"}}
    backend = FakeBackend(rows)
    updated = _apply_metadata_updates(backend, source_map)
    assert updated == 1
    assert backend.updates[0] == ("1", [], "feed")


def test_apply_tag_order_irrelevant():
    """Tags ["b", "a"] and ["a", "b"] should be considered equal."""
    rows = [{"id": "1", "source_name": "@x", "source_type": "twitter", "tags": '["b", "a"]'}]
    source_map = {"@x": {"tags": ["a", "b"], "source_type": "twitter"}}
    backend = FakeBackend(rows)
    updated = _apply_metadata_updates(backend, source_map)
    assert updated == 0


def test_apply_skips_unknown_sources():
    rows = [{"id": "1", "source_name": "Unknown", "source_type": "rss", "tags": "[]"}]
    source_map = {"@alice": {"tags": ["ai"], "source_type": "twitter"}}
    backend = FakeBackend(rows)
    updated = _apply_metadata_updates(backend, source_map)
    assert updated == 0


def test_apply_dry_run_no_writes(capsys):
    rows = [{"id": "1", "source_name": "@alice", "source_type": "twitter", "tags": '["old"]'}]
    source_map = {"@alice": {"tags": ["new"], "source_type": "twitter"}}
    backend = FakeBackend(rows)
    updated = _apply_metadata_updates(backend, source_map, dry_run=True)
    assert updated == 1
    assert backend.updates == []  # no actual writes
    captured = capsys.readouterr()
    assert "@alice" in captured.out


def test_apply_tags_as_list():
    """Backend rows may already have tags as a Python list (not JSON string)."""
    rows = [{"id": "1", "source_name": "@alice", "source_type": "twitter", "tags": ["old"]}]
    source_map = {"@alice": {"tags": ["new"], "source_type": "twitter"}}
    backend = FakeBackend(rows)
    updated = _apply_metadata_updates(backend, source_map)
    assert updated == 1


def test_apply_multiple_items():
    rows = [
        {"id": "1", "source_name": "@a", "source_type": "twitter", "tags": '["old"]'},
        {"id": "2", "source_name": "@b", "source_type": "twitter", "tags": '["old"]'},
        {"id": "3", "source_name": "@c", "source_type": "twitter", "tags": '["same"]'},
    ]
    source_map = {
        "@a": {"tags": ["new"], "source_type": "twitter"},
        "@b": {"tags": ["new"], "source_type": "twitter"},
        "@c": {"tags": ["same"], "source_type": "twitter"},
    }
    backend = FakeBackend(rows)
    updated = _apply_metadata_updates(backend, source_map)
    assert updated == 2
    assert len(backend.updates) == 2
