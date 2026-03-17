"""Tests for export merge logic (_parse_iso, _load_existing_items)."""

import json
from datetime import datetime, timezone

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
