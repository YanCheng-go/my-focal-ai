"""Tests for SupabaseBackend — uses mocked Supabase client."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from ainews.models import ContentItem


def _make_item(**overrides) -> ContentItem:
    defaults = {
        "id": "abc123",
        "url": "https://example.com/1",
        "title": "Test Article",
        "source_name": "Test Feed",
        "source_type": "rss",
        "tags": ["ai"],
        "fetched_at": datetime(2026, 3, 11, 12, 0, 0),
    }
    defaults.update(overrides)
    return ContentItem(**defaults)


@pytest.fixture
def mock_supabase():
    """Create a SupabaseBackend with a mocked supabase client."""
    mock_client = MagicMock()
    with patch("ainews.storage.supabase_backend.create_client", return_value=mock_client):
        from ainews.storage.supabase_backend import SupabaseBackend

        backend = SupabaseBackend("https://test.supabase.co", "test-key")
        yield backend, mock_client


class TestSupabaseBackendBasics:
    def test_close_is_noop(self, mock_supabase):
        backend, _ = mock_supabase
        backend.close()  # Should not raise

    def test_commit_is_noop(self, mock_supabase):
        backend, _ = mock_supabase
        backend.commit()  # Should not raise


class TestGetLastFetched:
    def test_returns_none_when_not_found(self, mock_supabase):
        backend, client = mock_supabase
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        assert backend.get_last_fetched("test-source") is None

    def test_returns_datetime_when_found(self, mock_supabase):
        backend, client = mock_supabase
        client.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"last_fetched_at": "2026-03-11T12:00:00"}])
        )
        result = backend.get_last_fetched("test-source")
        assert result == datetime(2026, 3, 11, 12, 0, 0)


class TestSetLastFetched:
    def test_upserts_timestamp(self, mock_supabase):
        backend, client = mock_supabase
        ts = datetime(2026, 3, 11, 12, 0, 0)
        backend.set_last_fetched("test-source", ts)
        client.rpc.assert_called_once_with(
            "upsert_source_state",
            {"p_source_key": "test-source", "p_last_fetched_at": ts.isoformat()},
        )


class TestGetExistingIds:
    def test_empty_list_returns_empty_set(self, mock_supabase):
        backend, _ = mock_supabase
        assert backend.get_existing_ids([]) == set()

    def test_returns_matching_ids(self, mock_supabase):
        backend, client = mock_supabase
        mock_chain = client.table.return_value.select.return_value.in_.return_value.execute
        mock_chain.return_value = MagicMock(data=[{"id": "abc"}, {"id": "def"}])
        result = backend.get_existing_ids(["abc", "def", "ghi"])
        assert result == {"abc", "def"}


class TestCountItems:
    def test_count_with_filters(self, mock_supabase):
        backend, client = mock_supabase
        # Build a mock chain that supports arbitrary filter method calls
        mock_q = MagicMock()
        mock_q.execute.return_value = MagicMock(count=42)
        # Each filter call returns the same mock for chaining
        for method in ["is_", "gte", "eq", "in_", "neq", "contains", "or_", "limit"]:
            getattr(mock_q, method).return_value = mock_q
        client.table.return_value.select.return_value = mock_q

        result = backend.count_items(source_type="rss", min_score=0.5)
        assert result == 42


class TestGetItems:
    def test_returns_content_items(self, mock_supabase):
        backend, client = mock_supabase
        mock_q = MagicMock()
        mock_q.execute.return_value = MagicMock(
            data=[
                {
                    "id": "abc123",
                    "url": "https://example.com/1",
                    "title": "Test",
                    "summary": "",
                    "content": "",
                    "source_name": "Feed",
                    "source_type": "rss",
                    "tags": ["ai"],
                    "author": "",
                    "published_at": None,
                    "fetched_at": "2026-03-11T12:00:00",
                    "score": 0.8,
                    "score_reason": "relevant",
                    "tier": "work",
                    "is_duplicate_of": None,
                }
            ]
        )
        for method in [
            "is_",
            "gte",
            "eq",
            "in_",
            "neq",
            "contains",
            "or_",
            "order",
            "range",
            "limit",
        ]:
            getattr(mock_q, method).return_value = mock_q
        client.table.return_value.select.return_value = mock_q

        items = backend.get_items(limit=10)
        assert len(items) == 1
        assert items[0].id == "abc123"
        assert isinstance(items[0], ContentItem)


class TestUpsertItem:
    def test_calls_rpc(self, mock_supabase):
        backend, client = mock_supabase
        item = _make_item()
        backend.upsert_item(item)
        client.rpc.assert_called_once()
        call_args = client.rpc.call_args
        assert call_args[0][0] == "upsert_item"
        assert call_args[0][1]["p_id"] == "abc123"


class TestIngestItems:
    def test_skips_existing_items(self, mock_supabase):
        backend, client = mock_supabase
        # get_existing_ids returns {"abc123"}
        mock_chain = client.table.return_value.select.return_value.in_.return_value.execute
        mock_chain.return_value = MagicMock(data=[{"id": "abc123"}])
        # set_last_fetched
        client.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        items = [_make_item(id="abc123"), _make_item(id="def456", url="https://example.com/2")]
        result = backend.ingest_items("test", items)
        # Only def456 is new
        assert result == 1


class TestDeleteSourceContent:
    def test_deletes_and_returns_count(self, mock_supabase):
        backend, client = mock_supabase
        # count query
        mock_count = MagicMock()
        mock_count.execute.return_value = MagicMock(count=3)
        for method in ["is_", "gte", "eq", "in_", "neq"]:
            getattr(mock_count, method).return_value = mock_count
        client.table.return_value.select.return_value = mock_count
        # delete chain
        client.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
            MagicMock()
        )

        result = backend.delete_source_content("Test Feed")
        assert result == 3


class TestUserIdScoping:
    """Tests that user_id is passed through to Supabase operations."""

    @pytest.fixture
    def scoped_backend(self):
        mock_client = MagicMock()
        with patch("ainews.storage.supabase_backend.create_client", return_value=mock_client):
            from ainews.storage.supabase_backend import SupabaseBackend

            backend = SupabaseBackend("https://test.supabase.co", "test-key", user_id="user-123")
            yield backend, mock_client

    def test_upsert_item_passes_user_id(self, scoped_backend):
        backend, client = scoped_backend
        item = _make_item()
        backend.upsert_item(item)
        call_args = client.rpc.call_args
        assert call_args[0][1]["p_user_id"] == "user-123"

    def test_set_last_fetched_includes_user_id(self, scoped_backend):
        backend, client = scoped_backend
        ts = datetime(2026, 3, 11, 12, 0, 0)
        backend.set_last_fetched("test-source", ts)
        client.rpc.assert_called_with(
            "upsert_source_state",
            {
                "p_source_key": "test-source",
                "p_last_fetched_at": ts.isoformat(),
                "p_user_id": "user-123",
            },
        )

    def test_get_existing_ids_filters_by_user_id(self, scoped_backend):
        backend, client = scoped_backend
        mock_chain = (
            client.table.return_value.select.return_value.in_.return_value.eq.return_value.execute
        )
        mock_chain.return_value = MagicMock(data=[{"id": "abc"}])
        backend.get_existing_ids(["abc", "def"])
        # Verify .eq("user_id", ...) was called
        client.table.return_value.select.return_value.in_.return_value.eq.assert_called_with(
            "user_id", "user-123"
        )

    def test_build_query_filters_by_user_id(self, scoped_backend):
        backend, client = scoped_backend
        mock_q = MagicMock()
        mock_q.execute.return_value = MagicMock(count=5)
        for method in ["is_", "gte", "eq", "in_", "neq", "contains", "or_", "limit"]:
            getattr(mock_q, method).return_value = mock_q
        client.table.return_value.select.return_value = mock_q

        backend.count_items()
        # eq should be called with user_id
        mock_q.eq.assert_any_call("user_id", "user-123")

    def test_get_source_health_passes_user_id(self, scoped_backend):
        backend, client = scoped_backend
        client.rpc.return_value.execute.return_value = MagicMock(data=[])
        q_mock = MagicMock()
        q_mock.execute.return_value = MagicMock(data=[])
        q_mock.eq.return_value = q_mock
        client.table.return_value.select.return_value = q_mock

        backend.get_source_health()
        client.rpc.assert_called_with("get_source_health", {"p_user_id": "user-123"})

    def test_get_all_tags_passes_user_id(self, scoped_backend):
        backend, client = scoped_backend
        client.rpc.return_value.execute.return_value = MagicMock(data=[])
        backend.get_all_tags()
        client.rpc.assert_called_with("get_all_tags", {"p_user_id": "user-123"})

    def test_no_user_id_means_no_filter(self, mock_supabase):
        """When user_id is None, no user_id filter is applied."""
        backend, client = mock_supabase
        assert backend._user_id is None
        item = _make_item()
        backend.upsert_item(item)
        call_args = client.rpc.call_args
        assert call_args[0][1]["p_user_id"] is None


class TestGetBackendFactory:
    def test_returns_sqlite_by_default(self, tmp_path):
        from ainews.storage.db import get_backend

        with patch("ainews.config.Settings") as mock_settings:
            mock_settings.return_value.supabase_url = ""
            mock_settings.return_value.supabase_key = ""
            mock_settings.return_value.db_path = tmp_path / "test.db"
            backend = get_backend()
            from ainews.storage.db import SqliteBackend

            assert isinstance(backend, SqliteBackend)
            backend.close()

    def test_returns_supabase_when_configured(self):
        from ainews.storage.db import get_backend

        mock_client = MagicMock()
        with (
            patch("ainews.config.Settings") as mock_settings,
            patch(
                "ainews.storage.supabase_backend.create_client",
                return_value=mock_client,
            ),
        ):
            mock_settings.return_value.supabase_url = "https://test.supabase.co"
            mock_settings.return_value.supabase_key = "test-key"
            mock_settings.return_value.supabase_service_key = ""
            backend = get_backend()
            from ainews.storage.supabase_backend import SupabaseBackend

            assert isinstance(backend, SupabaseBackend)

    def test_passes_user_id_to_supabase(self):
        from ainews.storage.db import get_backend

        mock_client = MagicMock()
        with (
            patch("ainews.config.Settings") as mock_settings,
            patch(
                "ainews.storage.supabase_backend.create_client",
                return_value=mock_client,
            ),
        ):
            mock_settings.return_value.supabase_url = "https://test.supabase.co"
            mock_settings.return_value.supabase_key = "test-key"
            mock_settings.return_value.supabase_service_key = "service-key"
            backend = get_backend(user_id="user-456")
            assert backend._user_id == "user-456"

    def test_uses_service_key_when_available(self):
        from ainews.storage.db import get_backend

        mock_client = MagicMock()
        with (
            patch("ainews.config.Settings") as mock_settings,
            patch(
                "ainews.storage.supabase_backend.create_client",
                return_value=mock_client,
            ) as mock_create,
        ):
            mock_settings.return_value.supabase_url = "https://test.supabase.co"
            mock_settings.return_value.supabase_key = "anon-key"
            mock_settings.return_value.supabase_service_key = "service-key"
            get_backend()
            mock_create.assert_called_with("https://test.supabase.co", "service-key")
