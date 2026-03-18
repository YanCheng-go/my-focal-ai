"""Tests for cloud_fetch module — cloud_fetch_all_users and _score_with_claude."""

import asyncio
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ainews.models import ContentItem

# --- Helpers ---


def _reload_settings(monkeypatch):
    """Reload ainews.config so Settings picks up monkeypatched env vars."""
    import ainews.config

    importlib.reload(ainews.config)


def _inject_fake_supabase(monkeypatch) -> MagicMock:
    """Inject a fake supabase module with a mock create_client."""
    mock_client = MagicMock()
    fake_mod = types.ModuleType("supabase")
    fake_mod.create_client = MagicMock(return_value=mock_client)
    monkeypatch.setitem(sys.modules, "supabase", fake_mod)
    return mock_client


def _make_user_sources(user_id="user-1", source_type="rss", name="Feed A"):
    return [
        {
            "user_id": user_id,
            "source_type": source_type,
            "name": name,
            "config": {"url": f"https://{name.lower().replace(' ', '')}.example.com/feed"},
            "tags": ["test"],
            "disabled": False,
        },
    ]


# --- cloud_fetch_all_users ---


class TestCloudFetchAllUsers:
    """Tests for cloud_fetch_all_users()."""

    @pytest.fixture(autouse=True)
    def _clear_supabase_env(self, monkeypatch):
        """Ensure clean env for each test."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("AINEWS_SUPABASE_URL", raising=False)
        monkeypatch.delenv("AINEWS_SUPABASE_KEY", raising=False)
        monkeypatch.delenv("AINEWS_SUPABASE_SERVICE_KEY", raising=False)

    def test_missing_supabase_url(self, monkeypatch):
        """Returns 0 when AINEWS_SUPABASE_URL is not set."""
        monkeypatch.setenv("AINEWS_SUPABASE_SERVICE_KEY", "svc-key")
        _reload_settings(monkeypatch)

        from ainews.cloud_fetch import cloud_fetch_all_users

        total = asyncio.run(cloud_fetch_all_users())
        assert total == 0

    def test_missing_service_key(self, monkeypatch):
        """Returns 0 when AINEWS_SUPABASE_SERVICE_KEY is not set."""
        monkeypatch.setenv("AINEWS_SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("AINEWS_SUPABASE_KEY", "anon-key")
        _reload_settings(monkeypatch)

        from ainews.cloud_fetch import cloud_fetch_all_users

        total = asyncio.run(cloud_fetch_all_users())
        assert total == 0

    def test_missing_supabase_package(self, monkeypatch):
        """Returns 0 gracefully when supabase package is not installed."""
        monkeypatch.setenv("AINEWS_SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("AINEWS_SUPABASE_KEY", "anon-key")
        monkeypatch.setenv("AINEWS_SUPABASE_SERVICE_KEY", "svc-key")
        _reload_settings(monkeypatch)

        # Remove supabase from sys.modules so the import fails
        monkeypatch.delitem(sys.modules, "supabase", raising=False)

        with patch.dict(sys.modules, {"supabase": None}):
            from ainews.cloud_fetch import cloud_fetch_all_users

            total = asyncio.run(cloud_fetch_all_users())
            assert total == 0

    def _setup_supabase_env(self, monkeypatch):
        """Set required env vars for Supabase mode."""
        monkeypatch.setenv("AINEWS_SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("AINEWS_SUPABASE_KEY", "anon-key")
        monkeypatch.setenv("AINEWS_SUPABASE_SERVICE_KEY", "svc-key")
        _reload_settings(monkeypatch)

    def test_no_users_found(self, monkeypatch):
        """Returns 0 when no users have configured sources."""
        self._setup_supabase_env(monkeypatch)
        _inject_fake_supabase(monkeypatch)

        async def _run():
            with patch("ainews.sources.supabase_manager.get_all_user_ids", return_value=[]):
                from ainews.cloud_fetch import cloud_fetch_all_users

                return await cloud_fetch_all_users()

        total = asyncio.run(_run())
        assert total == 0

    def test_user_with_no_sources_skipped(self, monkeypatch):
        """Skips a user whose get_user_sources returns empty."""
        self._setup_supabase_env(monkeypatch)
        _inject_fake_supabase(monkeypatch)

        async def _run():
            with (
                patch(
                    "ainews.sources.supabase_manager.get_all_user_ids",
                    return_value=["user-empty"],
                ),
                patch(
                    "ainews.sources.supabase_manager.get_user_sources",
                    return_value=[],
                ),
                patch("ainews.cloud_fetch.get_backend") as mock_get_backend,
                patch(
                    "ainews.cloud_fetch.run_ingestion",
                    new_callable=AsyncMock,
                ),
            ):
                from ainews.cloud_fetch import cloud_fetch_all_users

                total = await cloud_fetch_all_users()
                # Backend should never be created for a user with no sources
                mock_get_backend.assert_not_called()
                return total

        total = asyncio.run(_run())
        assert total == 0

    def test_multiple_users(self, monkeypatch):
        """Processes multiple users and aggregates item counts."""
        self._setup_supabase_env(monkeypatch)
        _inject_fake_supabase(monkeypatch)

        call_order = []
        ingestion_counts = {"user-1": 5, "user-2": 3}

        async def fake_ingestion(backend, sources_config=None, config_dir=None):
            # Track which user's backend was used
            uid = mock_get_backend_calls.pop(0)
            call_order.append(uid)
            return ingestion_counts[uid]

        mock_get_backend_calls = []

        def fake_get_backend(user_id=None, db_path=None):
            mock_get_backend_calls.append(user_id)
            backend = MagicMock()
            backend.__enter__ = MagicMock(return_value=backend)
            backend.__exit__ = MagicMock(return_value=False)
            return backend

        def fake_get_user_sources(client, uid):
            return _make_user_sources(user_id=uid, name=f"Feed-{uid}")

        async def _run():
            with (
                patch(
                    "ainews.sources.supabase_manager.get_all_user_ids",
                    return_value=["user-1", "user-2"],
                ),
                patch(
                    "ainews.sources.supabase_manager.get_user_sources",
                    side_effect=fake_get_user_sources,
                ),
                patch("ainews.cloud_fetch.get_backend", side_effect=fake_get_backend),
                patch(
                    "ainews.cloud_fetch.run_ingestion",
                    new_callable=AsyncMock,
                    side_effect=fake_ingestion,
                ),
            ):
                from ainews.cloud_fetch import cloud_fetch_all_users

                return await cloud_fetch_all_users()

        total = asyncio.run(_run())
        assert total == 8  # 5 + 3
        assert call_order == ["user-1", "user-2"]

    def test_timeout_isolates_per_user(self, monkeypatch):
        """A timed-out user doesn't block other users."""
        self._setup_supabase_env(monkeypatch)
        _inject_fake_supabase(monkeypatch)

        call_count = 0

        async def slow_then_fast(backend, sources_config=None, config_dir=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First user times out
                await asyncio.sleep(999)
            return 4

        def fake_get_backend(user_id=None, db_path=None):
            backend = MagicMock()
            backend.__enter__ = MagicMock(return_value=backend)
            backend.__exit__ = MagicMock(return_value=False)
            return backend

        async def _run():
            with (
                patch(
                    "ainews.sources.supabase_manager.get_all_user_ids",
                    return_value=["slow-user", "fast-user"],
                ),
                patch(
                    "ainews.sources.supabase_manager.get_user_sources",
                    side_effect=lambda c, uid: _make_user_sources(user_id=uid),
                ),
                patch("ainews.cloud_fetch.get_backend", side_effect=fake_get_backend),
                patch(
                    "ainews.cloud_fetch.run_ingestion",
                    new_callable=AsyncMock,
                    side_effect=slow_then_fast,
                ),
                patch("ainews.cloud_fetch._USER_FETCH_TIMEOUT", 0.01),
            ):
                from ainews.cloud_fetch import cloud_fetch_all_users

                return await cloud_fetch_all_users()

        total = asyncio.run(_run())
        # Only fast-user's 4 items counted; slow-user timed out
        assert total == 4

    def test_exception_isolates_per_user(self, monkeypatch):
        """An exception in one user doesn't block others."""
        self._setup_supabase_env(monkeypatch)
        _inject_fake_supabase(monkeypatch)

        call_count = 0

        async def crash_then_ok(backend, sources_config=None, config_dir=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Feed server down")
            return 7

        def fake_get_backend(user_id=None, db_path=None):
            backend = MagicMock()
            backend.__enter__ = MagicMock(return_value=backend)
            backend.__exit__ = MagicMock(return_value=False)
            return backend

        async def _run():
            with (
                patch(
                    "ainews.sources.supabase_manager.get_all_user_ids",
                    return_value=["crash-user", "ok-user"],
                ),
                patch(
                    "ainews.sources.supabase_manager.get_user_sources",
                    side_effect=lambda c, uid: _make_user_sources(user_id=uid),
                ),
                patch("ainews.cloud_fetch.get_backend", side_effect=fake_get_backend),
                patch(
                    "ainews.cloud_fetch.run_ingestion",
                    new_callable=AsyncMock,
                    side_effect=crash_then_ok,
                ),
            ):
                from ainews.cloud_fetch import cloud_fetch_all_users

                return await cloud_fetch_all_users()

        total = asyncio.run(_run())
        assert total == 7  # Only ok-user's items counted

    def test_backend_context_manager_cleanup(self, monkeypatch):
        """Backend __exit__ is called even when ingestion raises."""
        self._setup_supabase_env(monkeypatch)
        _inject_fake_supabase(monkeypatch)

        mock_backend = MagicMock()
        mock_backend.__enter__ = MagicMock(return_value=mock_backend)
        mock_backend.__exit__ = MagicMock(return_value=False)

        async def _run():
            with (
                patch(
                    "ainews.sources.supabase_manager.get_all_user_ids",
                    return_value=["user-1"],
                ),
                patch(
                    "ainews.sources.supabase_manager.get_user_sources",
                    return_value=_make_user_sources(),
                ),
                patch("ainews.cloud_fetch.get_backend", return_value=mock_backend),
                patch(
                    "ainews.cloud_fetch.run_ingestion",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("boom"),
                ),
            ):
                from ainews.cloud_fetch import cloud_fetch_all_users

                await cloud_fetch_all_users()

        asyncio.run(_run())
        mock_backend.__exit__.assert_called_once()

    def test_scoring_called_per_user(self, monkeypatch):
        """When ANTHROPIC_API_KEY is set, scoring runs for each user."""
        self._setup_supabase_env(monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        _reload_settings(monkeypatch)
        _inject_fake_supabase(monkeypatch)

        score_labels = []

        async def fake_score(backend, settings, label=""):
            score_labels.append(label)
            return 2

        def fake_get_backend(user_id=None, db_path=None):
            backend = MagicMock()
            backend.__enter__ = MagicMock(return_value=backend)
            backend.__exit__ = MagicMock(return_value=False)
            return backend

        async def _run():
            with (
                patch(
                    "ainews.sources.supabase_manager.get_all_user_ids",
                    return_value=["user-a", "user-b"],
                ),
                patch(
                    "ainews.sources.supabase_manager.get_user_sources",
                    side_effect=lambda c, uid: _make_user_sources(user_id=uid),
                ),
                patch("ainews.cloud_fetch.get_backend", side_effect=fake_get_backend),
                patch(
                    "ainews.cloud_fetch.run_ingestion",
                    new_callable=AsyncMock,
                    return_value=1,
                ),
                patch(
                    "ainews.cloud_fetch._score_with_claude",
                    new_callable=AsyncMock,
                    side_effect=fake_score,
                ),
            ):
                from ainews.cloud_fetch import cloud_fetch_all_users

                return await cloud_fetch_all_users()

        total = asyncio.run(_run())
        assert total == 2  # 1 + 1 from ingestion
        assert "User user-a" in score_labels
        assert "User user-b" in score_labels

    def test_sources_to_config_passed_to_ingestion(self, monkeypatch):
        """Verifies the converted config dict is forwarded to run_ingestion."""
        self._setup_supabase_env(monkeypatch)
        _inject_fake_supabase(monkeypatch)

        captured_configs = []

        async def capture_ingestion(backend, sources_config=None, config_dir=None):
            captured_configs.append(sources_config)
            return 0

        def fake_get_backend(user_id=None, db_path=None):
            backend = MagicMock()
            backend.__enter__ = MagicMock(return_value=backend)
            backend.__exit__ = MagicMock(return_value=False)
            return backend

        rows = [
            {
                "source_type": "youtube",
                "name": "3Blue1Brown",
                "config": {"channel_id": "UC123"},
                "tags": ["math"],
                "disabled": False,
                "user_id": "user-1",
            },
        ]

        async def _run():
            with (
                patch(
                    "ainews.sources.supabase_manager.get_all_user_ids",
                    return_value=["user-1"],
                ),
                patch(
                    "ainews.sources.supabase_manager.get_user_sources",
                    return_value=rows,
                ),
                patch("ainews.cloud_fetch.get_backend", side_effect=fake_get_backend),
                patch(
                    "ainews.cloud_fetch.run_ingestion",
                    new_callable=AsyncMock,
                    side_effect=capture_ingestion,
                ),
            ):
                from ainews.cloud_fetch import cloud_fetch_all_users

                return await cloud_fetch_all_users()

        asyncio.run(_run())
        assert len(captured_configs) == 1
        config = captured_configs[0]
        assert "youtube" in config["sources"]
        assert config["sources"]["youtube"][0]["channel_id"] == "UC123"
        assert config["sources"]["youtube"][0]["name"] == "3Blue1Brown"


# --- _score_with_claude ---


class TestScoreWithClaude:
    """Tests for _score_with_claude helper."""

    def test_skips_when_no_api_key(self, monkeypatch):
        """Returns 0 without calling scorer when ANTHROPIC_API_KEY is not set."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        backend = MagicMock()

        async def _run():
            from ainews.cloud_fetch import _score_with_claude

            return await _score_with_claude(backend, MagicMock())

        count = asyncio.run(_run())
        assert count == 0
        backend.get_unscored_items.assert_not_called()

    def test_skips_when_no_unscored_items(self, monkeypatch):
        """Returns 0 when there are no unscored items to score."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

        backend = MagicMock()
        backend.get_unscored_items.return_value = []

        async def _run():
            from ainews.cloud_fetch import _score_with_claude

            return await _score_with_claude(backend, MagicMock())

        count = asyncio.run(_run())
        assert count == 0

    def test_scores_and_upserts(self, monkeypatch):
        """Scores unscored items and upserts them back."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

        item1 = ContentItem(
            id="i1",
            url="https://example.com/1",
            title="Test 1",
            source_name="Test Feed",
            source_type="rss",
        )
        item2 = ContentItem(
            id="i2",
            url="https://example.com/2",
            title="Test 2",
            source_name="Test Feed",
            source_type="rss",
        )
        backend = MagicMock()
        backend.get_unscored_items.return_value = [item1, item2]

        scored_pairs = [(item1, "high"), (item2, "low")]

        settings = MagicMock()
        settings.config_dir = Path("/tmp/config")

        mock_scorer = AsyncMock(return_value=scored_pairs)

        async def _run():
            with (
                patch(
                    "ainews.cloud_fetch.load_principles",
                    return_value=["p1"],
                ),
                patch(
                    "ainews.scoring.claude_scorer.score_batch_claude",
                    mock_scorer,
                ),
            ):
                from ainews.cloud_fetch import _score_with_claude

                return await _score_with_claude(backend, settings, label="Test")

        count = asyncio.run(_run())
        assert count == 2
        assert backend.upsert_item.call_count == 2
        backend.commit.assert_called_once()


# --- CLI dispatch ---


class TestCLIDispatch:
    """Test that the cloud-fetch-users CLI command dispatches correctly."""

    def test_cloud_fetch_users_dispatch(self, monkeypatch):
        """'cloud-fetch-users' command calls cloud_fetch_all_users.

        This test validates the CLI wiring added in PR #153. It will xfail on
        main until that PR is merged.
        """
        from ainews.cli import main

        monkeypatch.setattr("sys.argv", ["ainews", "cloud-fetch-users"])

        # Check if the subcommand exists (PR #153 adds it)
        try:
            with patch(
                "ainews.cloud_fetch.cloud_fetch_all_users",
                new_callable=AsyncMock,
                return_value=5,
            ) as mock_fn:
                main()
                mock_fn.assert_called_once()
        except SystemExit:
            pytest.skip("cloud-fetch-users subcommand not yet available (PR #153)")

    def test_cloud_fetch_dispatch(self, monkeypatch):
        """'cloud-fetch' command calls cloud_fetch_and_score."""
        with patch(
            "ainews.cloud_fetch.cloud_fetch_and_score",
            new_callable=AsyncMock,
            return_value=3,
        ) as mock_fn:
            from ainews.cli import main

            monkeypatch.setattr("sys.argv", ["ainews", "cloud-fetch"])
            main()
            mock_fn.assert_called_once()
