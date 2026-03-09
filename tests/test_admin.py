"""Tests for admin UI source management."""

import pytest
from fastapi.testclient import TestClient

SAMPLE_SOURCES_YML = """\
# Source configuration for ai-news-filter
rsshub_base: "http://localhost:1200"

sources:
  # Twitter
  twitter:
    - handle: "testuser"
      tags: [ai]

  youtube:
    - channel_id: "UC123"
      name: "Test Channel"
      tags: [ai]

  rss:
    - url: "https://example.com/feed.xml"
      name: "Example Feed"
      tags: [test]

  rsshub:
    - route: "/test/route"
      name: "Test RSSHub"
      source_type: "rss"
      tags: [test]

  luma:
    - handle: "test-events"
      tags: [events]

  arxiv_queries:
    - query: "cat:cs.AI"
      name: "arXiv test"
      tags: [ai]
"""


@pytest.fixture
def config_dir(tmp_path):
    """Create a temp config dir with sample sources.yml."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yml").write_text(SAMPLE_SOURCES_YML)
    # Also need a principles.yml for Settings
    (cfg / "principles.yml").write_text("principles: []\n")
    return cfg


@pytest.fixture
def app_client(config_dir, tmp_path, monkeypatch):
    """Create a test client with patched config/db paths."""
    monkeypatch.setenv("AINEWS_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("AINEWS_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("AINEWS_SCORING", "false")

    # Need to reload modules so Settings picks up env vars
    import importlib

    import ainews.api.admin
    import ainews.api.app
    import ainews.config

    importlib.reload(ainews.config)
    importlib.reload(ainews.api.admin)
    importlib.reload(ainews.api.app)

    client = TestClient(ainews.api.app.app, raise_server_exceptions=False)
    yield client


# === Source Manager Unit Tests ===


class TestSourceManager:
    def test_load_sources(self, config_dir):
        from ainews.sources.manager import load_sources_roundtrip

        data = load_sources_roundtrip(config_dir)
        assert "sources" in data
        assert len(data["sources"]["twitter"]) == 1

    def test_add_rss_source(self, config_dir):
        from ainews.sources.manager import add_source, load_sources_roundtrip

        add_source(
            config_dir,
            "rss",
            {"url": "https://new.com/feed", "name": "New Feed", "tags": ["new"]},
        )
        data = load_sources_roundtrip(config_dir)
        assert len(data["sources"]["rss"]) == 2
        assert data["sources"]["rss"][1]["name"] == "New Feed"

    def test_add_twitter_source(self, config_dir):
        from ainews.sources.manager import add_source, load_sources_roundtrip

        add_source(config_dir, "twitter", {"handle": "newuser"})
        data = load_sources_roundtrip(config_dir)
        assert len(data["sources"]["twitter"]) == 2

    def test_add_arxiv_query(self, config_dir):
        from ainews.sources.manager import add_source, load_sources_roundtrip

        add_source(config_dir, "arxiv_queries", {"query": "cat:cs.CL", "name": "NLP"})
        data = load_sources_roundtrip(config_dir)
        assert len(data["sources"]["arxiv_queries"]) == 2

    def test_update_source(self, config_dir):
        from ainews.sources.manager import load_sources_roundtrip, update_source

        update_source(
            config_dir,
            "rss",
            0,
            {"url": "https://updated.com/feed", "name": "Updated", "tags": ["updated"]},
        )
        data = load_sources_roundtrip(config_dir)
        assert data["sources"]["rss"][0]["name"] == "Updated"

    def test_delete_source(self, config_dir):
        from ainews.sources.manager import delete_source, load_sources_roundtrip

        delete_source(config_dir, "twitter", 0)
        data = load_sources_roundtrip(config_dir)
        assert len(data["sources"]["twitter"]) == 0

    def test_toggle_source(self, config_dir):
        from ainews.sources.manager import load_sources_roundtrip, toggle_source

        toggle_source(config_dir, "rss", 0)
        data = load_sources_roundtrip(config_dir)
        assert data["sources"]["rss"][0]["disabled"] is True

        toggle_source(config_dir, "rss", 0)
        data = load_sources_roundtrip(config_dir)
        assert "disabled" not in data["sources"]["rss"][0]

    def test_validate_missing_field(self, config_dir):
        from ainews.sources.manager import add_source

        with pytest.raises(ValueError, match="Missing required field"):
            add_source(config_dir, "rss", {"name": "No URL"})

    def test_validate_invalid_type(self, config_dir):
        from ainews.sources.manager import add_source

        with pytest.raises(ValueError, match="Unknown source type"):
            add_source(config_dir, "invalid_type", {"name": "test"})

    def test_delete_out_of_range(self, config_dir):
        from ainews.sources.manager import delete_source

        with pytest.raises(IndexError):
            delete_source(config_dir, "twitter", 99)

    def test_roundtrip_preserves_comments(self, config_dir):
        from ainews.sources.manager import add_source

        add_source(config_dir, "rss", {"url": "https://new.com/feed", "name": "New"})
        content = (config_dir / "sources.yml").read_text()
        # The rsshub_base and sources structure should be preserved
        assert "rsshub_base" in content

    def test_get_all_sources_flat(self, config_dir):
        from ainews.sources.manager import get_all_sources_flat

        sources = get_all_sources_flat(config_dir)
        names = [s["name"] for s in sources]
        assert "@testuser" in names
        assert "Test Channel" in names
        assert "Example Feed" in names
        assert "arXiv test" in names
        assert "Luma: test-events" in names


# === DB Health Query Test ===


class TestSourceHealth:
    def test_get_source_health_empty(self, tmp_path):
        from ainews.storage.db import get_db, get_source_health

        conn = get_db(tmp_path / "test.db")
        health = get_source_health(conn)
        assert health == {}
        conn.close()

    def test_get_source_health_with_items(self, tmp_path):
        from ainews.models import ContentItem
        from ainews.storage.db import get_db, get_source_health, upsert_item

        conn = get_db(tmp_path / "test.db")
        item = ContentItem(
            id="test1",
            url="https://example.com/1",
            title="Test",
            source_name="Example Feed",
            source_type="rss",
            tags=["test"],
        )
        upsert_item(conn, item)
        conn.commit()
        health = get_source_health(conn)
        assert "Example Feed" in health
        assert health["Example Feed"]["item_count"] == 1
        conn.close()
