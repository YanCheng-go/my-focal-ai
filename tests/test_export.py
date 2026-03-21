"""Tests for export merge logic (_parse_iso, _load_existing_items) and pruning."""

import json
from datetime import datetime, timedelta, timezone

from ainews.export import _load_existing_items, _parse_iso

UTC_MIN = datetime.min.replace(tzinfo=timezone.utc)


class TestParseIso:
    def test_z_suffix(self):
        dt = _parse_iso("2026-03-17T12:00:00Z")
        assert dt == datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)

    def test_offset(self):
        dt = _parse_iso("2026-03-17T12:00:00+00:00")
        assert dt == datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)

    def test_empty_string(self):
        assert _parse_iso("") is None

    def test_invalid(self):
        assert _parse_iso("not-a-date") is None


class TestLoadExistingItems:
    def test_nonexistent_file(self, tmp_path):
        result = _load_existing_items(tmp_path / "missing.json", UTC_MIN)
        assert result == []

    def test_filters_by_time_window(self, tmp_path):
        path = tmp_path / "data.json"
        since = datetime(2026, 3, 16, 0, 0, 0, tzinfo=timezone.utc)
        items = [
            {"url": "https://a.com", "published_at": "2026-03-17T10:00:00Z"},
            {"url": "https://old.com", "published_at": "2026-03-10T10:00:00Z"},
            {"url": "https://b.com", "fetched_at": "2026-03-16T12:00:00Z"},
        ]
        path.write_text(json.dumps({"items": items}))

        result = _load_existing_items(path, since)
        urls = [i["url"] for i in result]
        assert "https://a.com" in urls
        assert "https://b.com" in urls
        assert "https://old.com" not in urls

    def test_falls_back_to_fetched_at(self, tmp_path):
        path = tmp_path / "data.json"
        since = datetime(2026, 3, 16, 0, 0, 0, tzinfo=timezone.utc)
        items = [
            {"url": "https://no-pub.com", "fetched_at": "2026-03-17T10:00:00Z"},
        ]
        path.write_text(json.dumps({"items": items}))

        result = _load_existing_items(path, since)
        assert len(result) == 1

    def test_corrupt_json(self, tmp_path):
        path = tmp_path / "data.json"
        path.write_text("not valid json{{{")

        result = _load_existing_items(path, UTC_MIN)
        assert result == []

    def test_skips_items_without_dates(self, tmp_path):
        path = tmp_path / "data.json"
        items = [{"url": "https://no-date.com"}]
        path.write_text(json.dumps({"items": items}))

        result = _load_existing_items(path, UTC_MIN)
        assert result == []


class TestAppendPruning:
    """Test that append_source_type prunes old items from data.json."""

    def _write_data_json(self, path, items):
        path.write_text(
            json.dumps(
                {
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "total": len(items),
                    "items": items,
                }
            )
        )

    def test_old_items_pruned_on_append(self, tmp_path, monkeypatch):
        """Items older than the time window are removed from data.json."""
        from unittest.mock import MagicMock

        from ainews import export

        path = tmp_path / "data.json"
        now = datetime.now(timezone.utc)
        old_item = {
            "url": "https://old.com",
            "title": "Old",
            "published_at": (now - timedelta(days=10)).isoformat(),
            "source_type": "rss",
        }
        recent_item = {
            "url": "https://recent.com",
            "title": "Recent",
            "published_at": (now - timedelta(hours=12)).isoformat(),
            "source_type": "rss",
        }
        self._write_data_json(path, [old_item, recent_item])

        # Mock the backend to return no new items
        mock_backend = MagicMock()
        mock_backend.get_items.return_value = []
        mock_backend.__enter__ = MagicMock(return_value=mock_backend)
        mock_backend.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr(export, "get_backend", lambda *a, **kw: mock_backend)
        monkeypatch.setattr(export, "_export_config", lambda *a, **kw: None)

        # hours=168 (7 days) — old_item (10 days ago) should be pruned
        export.append_source_type(path, source_type="rss", hours=168)

        with open(path) as f:
            data = json.load(f)
        urls = [i["url"] for i in data["items"]]
        assert "https://recent.com" in urls
        assert "https://old.com" not in urls

    def test_no_write_when_nothing_to_prune_or_append(self, tmp_path, monkeypatch):
        """When all items are recent and no new items, file is untouched."""
        from unittest.mock import MagicMock

        from ainews import export

        path = tmp_path / "data.json"
        now = datetime.now(timezone.utc)
        recent_item = {
            "url": "https://recent.com",
            "title": "Recent",
            "published_at": (now - timedelta(hours=1)).isoformat(),
            "source_type": "twitter",
        }
        self._write_data_json(path, [recent_item])

        mock_backend = MagicMock()
        mock_backend.get_items.return_value = []
        mock_backend.__enter__ = MagicMock(return_value=mock_backend)
        mock_backend.__exit__ = MagicMock(return_value=False)
        monkeypatch.setattr(export, "get_backend", lambda *a, **kw: mock_backend)
        monkeypatch.setattr(export, "_export_config", lambda *a, **kw: None)

        result = export.append_source_type(path, source_type="twitter", hours=168)
        assert result == 0
