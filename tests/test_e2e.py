"""End-to-end tests for all three deployment modes.

Mode 1: Local — SQLite + FastAPI + mocked Ollama scoring
Mode 2: Online Public — cloud_fetch + export to static JSON
Mode 3: Online Login — SupabaseBackend with user isolation
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ainews.models import ContentItem, make_id

# --- Shared fixtures ---

SAMPLE_SOURCES_YML = """\
rsshub_base: "http://localhost:1200"

sources:
  rss:
    - url: "https://example.com/feed.xml"
      name: "Example Feed"
      tags: [test]

  youtube:
    - channel_id: "UC123"
      name: "Test Channel"
      tags: [ai]

  leaderboard:
    - name: "Test Board"
      url: "https://example.com/board"

  event_links:
    - name: "Test Event"
      url: "https://example.com/event"
"""

SAMPLE_FEED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>Test Article 1</title>
      <link>https://example.com/article-1</link>
      <description>First test article</description>
      <pubDate>Mon, 10 Mar 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Test Article 2</title>
      <link>https://example.com/article-2</link>
      <description>Second test article</description>
      <pubDate>Mon, 10 Mar 2026 13:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_YT_FEED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Test Channel</title>
  <entry>
    <title>Test Video</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=abc123"/>
    <published>2026-03-10T12:00:00+00:00</published>
    <author><name>Test Channel</name></author>
  </entry>
</feed>
"""


def _mock_non_rss_ingesters():
    """Context manager that mocks out Twitter, XHS, events, trending, and metadata sync.

    Patches at the source modules so the lazy imports inside run_ingestion()
    pick up the mocked versions.
    """
    from contextlib import ExitStack

    return ExitStack(), [
        patch(
            "ainews.ingest.twitter.run_twitter_ingestion", new_callable=AsyncMock, return_value=0
        ),
        patch(
            "ainews.ingest.xiaohongshu.run_xhs_ingestion", new_callable=AsyncMock, return_value=0
        ),
        patch("ainews.ingest.events.run_events_ingestion", new_callable=AsyncMock, return_value=0),
        patch(
            "ainews.ingest.github_trending.run_github_trending_ingestion",
            new_callable=AsyncMock,
            return_value=0,
        ),
        patch("ainews.backfill.sync_source_metadata"),
    ]


@pytest.fixture
def config_dir(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sources.yml").write_text(SAMPLE_SOURCES_YML)
    (cfg / "principles.yml").write_text("principles: []\ntiers: {}\n")
    return cfg


@pytest.fixture
def sqlite_backend(tmp_path):
    from ainews.storage.db import SqliteBackend

    backend = SqliteBackend(tmp_path / "test.db")
    yield backend
    backend.close()


def _make_item(
    url="https://example.com/1",
    title="Test",
    source_name="Example Feed",
    source_type="rss",
    tags=None,
    score=None,
    user_id=None,
):
    """Helper to create a ContentItem."""
    return ContentItem(
        id=make_id(url, user_id),
        url=url,
        title=title,
        source_name=source_name,
        source_type=source_type,
        tags=tags or ["test"],
        score=score,
    )


# ============================================================
# Mode 1: Local — SQLite + FastAPI + Ollama
# ============================================================


class TestMode1Local:
    """E2E tests for local mode: ingest → store → score → serve."""

    def test_ingest_store_serve(self, sqlite_backend, config_dir):
        """Full pipeline: ingest RSS items, store in SQLite, query via backend."""
        # Seed items directly (simulating what runner would do after fetch)
        items = [_make_item(f"https://example.com/{i}", f"Article {i}") for i in range(5)]
        new_count = sqlite_backend.ingest_items("Example Feed", items)

        assert new_count == 5

        # Query items back
        stored = sqlite_backend.get_items(limit=10)
        assert len(stored) == 5

        # Verify dedup — re-ingest same items
        dup_count = sqlite_backend.ingest_items("Example Feed", items)
        assert dup_count == 0

    def test_score_preserves_on_reingest(self, sqlite_backend):
        """Score is preserved when an item is re-ingested without a score."""
        item = _make_item(score=0.85)
        sqlite_backend.upsert_item(item)
        sqlite_backend.commit()

        # Re-ingest without score
        item_no_score = _make_item(score=None)
        sqlite_backend.upsert_item(item_no_score)
        sqlite_backend.commit()

        stored = sqlite_backend.get_items(limit=1)
        assert stored[0].score == 0.85

    def test_youtube_shorts_dedup(self, sqlite_backend):
        """YouTube Shorts are marked as duplicates of matching full videos."""
        full = _make_item(
            url="https://www.youtube.com/watch?v=abc123",
            title="My Video",
            source_name="TestChannel",
            source_type="youtube",
        )
        short = _make_item(
            url="https://www.youtube.com/shorts/xyz789",
            title="My Video",
            source_name="TestChannel",
            source_type="youtube",
        )
        sqlite_backend.upsert_item(full)
        sqlite_backend.upsert_item(short)
        sqlite_backend.commit()

        dupes = sqlite_backend.mark_youtube_shorts_duplicates()
        assert dupes == 1

        # Short should be filtered out of get_items
        items = sqlite_backend.get_items(limit=10)
        urls = [i.url for i in items]
        assert "https://www.youtube.com/watch?v=abc123" in urls
        assert "https://www.youtube.com/shorts/xyz789" not in urls

    def test_ingest_from_feed(self, sqlite_backend, config_dir):
        """Ingest from a mocked RSS feed via the real runner pipeline."""
        import httpx

        mock_request = httpx.Request("GET", "https://example.com/feed.xml")
        mock_response = httpx.Response(200, text=SAMPLE_FEED_XML, request=mock_request)

        async def _run():
            with patch("ainews.ingest.feeds.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                stack, patches = _mock_non_rss_ingesters()
                with stack:
                    for p in patches:
                        stack.enter_context(p)
                    from ainews.ingest.runner import run_ingestion

                    return await run_ingestion(sqlite_backend, config_dir)

        total_new = asyncio.get_event_loop().run_until_complete(_run())

        assert total_new >= 2
        items = sqlite_backend.get_items(limit=10)
        titles = [i.title for i in items]
        assert "Test Article 1" in titles
        assert "Test Article 2" in titles

    def test_fastapi_dashboard(self, config_dir, tmp_path, monkeypatch):
        """FastAPI serves dashboard with items from SQLite."""
        import importlib
        import shutil

        import ainews.api.admin
        import ainews.api.app
        import ainews.config

        monkeypatch.setenv("AINEWS_CONFIG_DIR", str(config_dir))
        monkeypatch.setenv("AINEWS_DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setenv("AINEWS_SCORING", "false")
        monkeypatch.delenv("AINEWS_SUPABASE_URL", raising=False)
        monkeypatch.delenv("AINEWS_SUPABASE_KEY", raising=False)
        # Create static dir so FastAPI static mount doesn't fail
        (config_dir.parent / "static").mkdir(exist_ok=True)
        # Copy real templates so Jinja2 rendering works
        real_templates = Path(__file__).resolve().parent.parent / "templates"
        shutil.copytree(real_templates, config_dir.parent / "templates")

        importlib.reload(ainews.config)
        importlib.reload(ainews.api.admin)
        importlib.reload(ainews.api.app)

        # Seed data
        from ainews.storage.db import SqliteBackend

        backend = SqliteBackend(tmp_path / "test.db")
        for i in range(3):
            backend.upsert_item(_make_item(f"https://example.com/{i}", f"Article {i}"))
        backend.commit()
        backend.close()

        client = TestClient(ainews.api.app.app, raise_server_exceptions=False)

        # JSON API
        resp = client.get("/api/items")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

        # HTML dashboard
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Article 0" in resp.text

    def test_api_filters(self, config_dir, tmp_path, monkeypatch):
        """API filters work: tag, search, source_type."""
        import importlib
        import shutil

        import ainews.api.admin
        import ainews.api.app
        import ainews.config

        monkeypatch.setenv("AINEWS_CONFIG_DIR", str(config_dir))
        monkeypatch.setenv("AINEWS_DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setenv("AINEWS_SCORING", "false")
        monkeypatch.delenv("AINEWS_SUPABASE_URL", raising=False)
        monkeypatch.delenv("AINEWS_SUPABASE_KEY", raising=False)
        (config_dir.parent / "static").mkdir(exist_ok=True)
        real_templates = Path(__file__).resolve().parent.parent / "templates"
        if not (config_dir.parent / "templates").exists():
            shutil.copytree(real_templates, config_dir.parent / "templates")

        importlib.reload(ainews.config)
        importlib.reload(ainews.api.admin)
        importlib.reload(ainews.api.app)

        from ainews.storage.db import SqliteBackend

        backend = SqliteBackend(tmp_path / "test.db")
        backend.upsert_item(_make_item("https://a.com/1", "AI Paper", tags=["ai"]))
        backend.upsert_item(
            _make_item("https://b.com/2", "Web News", tags=["web"], source_type="youtube")
        )
        backend.commit()
        backend.close()

        client = TestClient(ainews.api.app.app, raise_server_exceptions=False)

        # Filter by tag
        resp = client.get("/api/items?tag=ai")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["title"] == "AI Paper"

        # Filter by search
        resp = client.get("/api/items?search=Web")
        assert resp.json()["total"] == 1

        # Filter by source_type
        resp = client.get("/api/items?source_type=youtube")
        assert resp.json()["total"] == 1


# ============================================================
# Mode 2: Online Public — cloud_fetch + export + static JSON
# ============================================================


class TestMode2OnlinePublic:
    """E2E tests for online public mode: fetch → SQLite → export → JSON."""

    def test_export_items(self, sqlite_backend, config_dir, tmp_path, monkeypatch):
        """Export scored items to data.json with correct structure."""
        monkeypatch.setenv("AINEWS_CONFIG_DIR", str(config_dir))
        monkeypatch.setenv("AINEWS_DB_PATH", str(tmp_path / "test.db"))

        # Seed items
        for i in range(5):
            sqlite_backend.upsert_item(
                _make_item(f"https://example.com/{i}", f"Article {i}", score=0.5 + i * 0.1)
            )
        sqlite_backend.commit()

        output = tmp_path / "static" / "data.json"
        from ainews.export import export_items

        count = export_items(output, hours=168)

        assert output.exists()
        assert count == 5

        data = json.loads(output.read_text())
        assert "items" in data
        assert "all_tags" in data
        assert "exported_at" in data
        assert len(data["items"]) == 5

    def test_export_config(self, config_dir, tmp_path, monkeypatch):
        """Export config.json with leaderboard and event links."""
        monkeypatch.setenv("AINEWS_CONFIG_DIR", str(config_dir))
        monkeypatch.setenv("AINEWS_DB_PATH", str(tmp_path / "test.db"))

        # Need to seed at least one item so export doesn't fail
        from ainews.storage.db import SqliteBackend

        backend = SqliteBackend(tmp_path / "test.db")
        backend.upsert_item(_make_item())
        backend.commit()
        backend.close()

        output = tmp_path / "static" / "data.json"
        from ainews.export import export_items

        export_items(output, hours=168)

        config_path = tmp_path / "static" / "config.json"
        assert config_path.exists()

        config = json.loads(config_path.read_text())
        assert "leaderboard" in config
        assert "event_links" in config
        assert "source_type_schema" in config
        assert config["leaderboard"][0]["name"] == "Test Board"

    def test_cloud_fetch_pipeline(self, config_dir, tmp_path, monkeypatch):
        """cloud_fetch_and_score() fetches feeds and stores items."""
        import httpx

        monkeypatch.setenv("AINEWS_CONFIG_DIR", str(config_dir))
        monkeypatch.setenv("AINEWS_DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setenv("AINEWS_SCORING", "false")
        monkeypatch.delenv("AINEWS_SUPABASE_URL", raising=False)
        monkeypatch.delenv("AINEWS_SUPABASE_KEY", raising=False)

        import importlib

        import ainews.config

        importlib.reload(ainews.config)

        mock_request = httpx.Request("GET", "https://example.com/feed.xml")
        mock_response = httpx.Response(200, text=SAMPLE_FEED_XML, request=mock_request)

        async def _run():
            with patch("ainews.ingest.feeds.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                stack, patches = _mock_non_rss_ingesters()
                with stack:
                    for p in patches:
                        stack.enter_context(p)
                    from ainews.cloud_fetch import cloud_fetch_and_score

                    return await cloud_fetch_and_score()

        total_new = asyncio.get_event_loop().run_until_complete(_run())
        assert total_new >= 2

    def test_vercel_env_disables_scheduler(self, monkeypatch):
        """VERCEL env var disables APScheduler."""
        monkeypatch.setenv("VERCEL", "1")

        import importlib

        import ainews.api.app

        importlib.reload(ainews.api.app)

        # The app should exist but without scheduler
        assert ainews.api.app._on_vercel is True


# ============================================================
# Mode 3: Online Login — Supabase + user isolation
# ============================================================


class TestMode3OnlineLogin:
    """E2E tests for online login mode: user-scoped SupabaseBackend."""

    def test_supabase_backend_ingest_reids_items(self):
        """SupabaseBackend.ingest_items re-IDs items with user_id prefix."""
        mock_client = MagicMock()
        tbl = mock_client.table.return_value
        sel = tbl.select.return_value.in_.return_value
        sel.eq.return_value.execute.return_value = MagicMock(data=[])

        with patch("ainews.storage.supabase_backend.create_client", return_value=mock_client):
            from ainews.storage.supabase_backend import SupabaseBackend

            backend = SupabaseBackend("https://test.supabase.co", "key", user_id="user-123")

            item = _make_item("https://example.com/1")
            original_id = item.id

            # Mock the RPC call
            mock_client.rpc.return_value.execute.return_value = MagicMock(data=None)

            backend.ingest_items("test-source", [item])

            # ID should have been changed to user-scoped version
            expected_id = make_id("https://example.com/1", "user-123")
            assert item.id == expected_id
            assert item.id != original_id

    def test_cloud_fetch_all_users(self, monkeypatch):
        """cloud_fetch_all_users iterates user_ids and creates scoped backends."""
        import importlib
        import sys
        import types

        monkeypatch.setenv("AINEWS_SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("AINEWS_SUPABASE_KEY", "anon-key")
        monkeypatch.setenv("AINEWS_SUPABASE_SERVICE_KEY", "service-key")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        import ainews.config

        importlib.reload(ainews.config)

        mock_service_client = MagicMock()

        # Ensure supabase module exists for the lazy import inside cloud_fetch_all_users
        fake_supabase = types.ModuleType("supabase")
        fake_supabase.create_client = MagicMock(return_value=mock_service_client)
        monkeypatch.setitem(sys.modules, "supabase", fake_supabase)

        user_sources = [
            {
                "user_id": "user-1",
                "source_type": "rss",
                "name": "Feed A",
                "config": {"url": "https://a.com/feed"},
                "tags": ["test"],
                "disabled": False,
            },
        ]

        async def _run():
            p2 = patch("ainews.sources.supabase_manager.get_all_user_ids", return_value=["user-1"])
            p3 = patch(
                "ainews.sources.supabase_manager.get_user_sources", return_value=user_sources
            )
            p4 = patch("ainews.cloud_fetch.get_backend")
            p5 = patch("ainews.cloud_fetch.run_ingestion", new_callable=AsyncMock, return_value=3)
            with p2, p3, p4 as mock_get_backend, p5:
                mock_backend = MagicMock()
                mock_get_backend.return_value = mock_backend

                from ainews.cloud_fetch import cloud_fetch_all_users

                total = await cloud_fetch_all_users()

                mock_get_backend.assert_called_once_with(user_id="user-1")
                mock_backend.close.assert_called_once()
                return total

        total = asyncio.get_event_loop().run_until_complete(_run())
        assert total == 3


# ============================================================
# Serverless Function — api/fetch-source.py smoke tests
# ============================================================


class TestServerlessFunction:
    """Smoke tests for the Vercel serverless function (api/fetch-source.py)."""

    @pytest.fixture(autouse=True)
    def _fake_supabase(self, monkeypatch):
        """Ensure a fake 'supabase' module with create_client exists."""
        import sys
        import types

        fake = types.ModuleType("supabase")
        fake.create_client = MagicMock()
        monkeypatch.setitem(sys.modules, "supabase", fake)

    def _import_handler(self):
        """Import the handler module from api/fetch-source.py."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "fetch_source", Path(__file__).resolve().parent.parent / "api" / "fetch_source.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_is_safe_url_blocks_private(self):
        """SSRF protection blocks private/internal URLs."""
        mod = self._import_handler()
        assert mod._is_safe_url("https://example.com/feed") is True
        assert mod._is_safe_url("http://localhost/secret") is False
        assert mod._is_safe_url("http://127.0.0.1/secret") is False
        assert mod._is_safe_url("http://192.168.1.1/secret") is False
        assert mod._is_safe_url("http://10.0.0.1/secret") is False
        assert mod._is_safe_url("http://169.254.169.254/latest") is False
        assert mod._is_safe_url("http://metadata.google.internal/") is False

    def test_build_feed_url_rss(self):
        """_build_feed_url converts source types to feed URLs."""
        mod = self._import_handler()
        result = mod._build_feed_url("rss", "HN", {"url": "https://hn.example.com/rss"})
        assert result == {
            "url": "https://hn.example.com/rss",
            "source_name": "HN",
            "source_type": "rss",
        }

    def test_build_feed_url_youtube(self):
        mod = self._import_handler()
        result = mod._build_feed_url("youtube", "Channel", {"channel_id": "UC123"})
        assert "UC123" in result["url"]
        assert result["source_type"] == "youtube"

    def test_build_feed_url_unknown_returns_none(self):
        mod = self._import_handler()
        assert mod._build_feed_url("twitter", "someone", {}) is None

    def test_make_id_user_scoped(self):
        """Item IDs are scoped to user_id."""
        mod = self._import_handler()
        id1 = mod._make_id("https://example.com/1", "user-a")
        id2 = mod._make_id("https://example.com/1", "user-b")
        id3 = mod._make_id("https://example.com/1")
        assert id1 != id2
        assert id1 != id3

    def test_handler_rejects_missing_auth(self):
        """Handler returns 401 when Authorization header is missing."""
        from io import BytesIO

        mod = self._import_handler()

        # Simulate a POST request with no auth header
        request_body = json.dumps({"source_type": "rss", "name": "Test"}).encode()
        wfile = BytesIO()

        h = mod.handler.__new__(mod.handler)
        h.headers = {"Content-Length": str(len(request_body))}
        h.rfile = BytesIO(request_body)
        h.wfile = wfile
        h.requestline = "POST /api/fetch-source HTTP/1.1"
        h.request_version = "HTTP/1.1"
        h.command = "POST"

        responses = []
        h.send_response = lambda code: responses.append(code)
        h.send_header = lambda *a: None
        h.end_headers = lambda: None

        h.do_POST()

        assert responses[0] == 401
        assert b"Missing Authorization" in wfile.getvalue()

    def test_handler_validates_input(self, monkeypatch):
        """Handler returns 400 for invalid source_type."""
        from io import BytesIO

        monkeypatch.setenv("AINEWS_SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("AINEWS_SUPABASE_KEY", "anon-key")
        monkeypatch.setenv("AINEWS_SUPABASE_SERVICE_KEY", "service-key")

        mod = self._import_handler()

        # Mock auth to succeed
        mock_client = MagicMock()
        mock_user = MagicMock()
        mock_user.user.id = "user-123"
        mock_client.auth.get_user.return_value = mock_user

        request_body = json.dumps(
            {
                "source_type": "twitter",  # unsupported in serverless
                "name": "someone",
                "config": {},
                "tags": [],
            }
        ).encode()

        wfile = BytesIO()
        h = mod.handler.__new__(mod.handler)
        h.headers = {
            "Content-Length": str(len(request_body)),
            "Authorization": "Bearer fake-jwt",
            "Origin": "",
        }
        h.rfile = BytesIO(request_body)
        h.wfile = wfile
        h.requestline = "POST /api/fetch-source HTTP/1.1"
        h.request_version = "HTTP/1.1"
        h.command = "POST"

        responses = []
        h.send_response = lambda code: responses.append(code)
        h.send_header = lambda *a: None
        h.end_headers = lambda: None

        with patch.object(mod, "create_client", return_value=mock_client):
            h.do_POST()

        assert responses[0] == 400
        assert b"Unsupported source_type" in wfile.getvalue()

    def test_cors_denies_when_unconfigured(self, monkeypatch):
        """CORS header is not sent when AINEWS_CORS_ORIGIN is unset."""
        from io import BytesIO

        monkeypatch.delenv("AINEWS_CORS_ORIGIN", raising=False)
        mod = self._import_handler()

        wfile = BytesIO()
        h = mod.handler.__new__(mod.handler)
        h.headers = {"Origin": "https://evil.com"}
        h.wfile = wfile
        h.requestline = "OPTIONS /api/fetch-source HTTP/1.1"
        h.request_version = "HTTP/1.1"
        h.command = "OPTIONS"

        sent_headers = {}
        h.send_response = lambda code: None
        h.send_header = lambda k, v: sent_headers.update({k: v})
        h.end_headers = lambda: None

        h.do_OPTIONS()

        assert "Access-Control-Allow-Origin" not in sent_headers
