"""Tests for SQLite backend — filters, chunking, tag sync, and CRUD."""

from datetime import datetime, timezone

import pytest

from ainews.models import ContentItem
from ainews.storage.db import SqliteBackend


@pytest.fixture
def db(tmp_path):
    backend = SqliteBackend(tmp_path / "test.db")
    yield backend
    backend.close()


def _item(id="item1", url="https://example.com/1", title="Test", **kwargs):
    defaults = dict(
        source_name="TestSource",
        source_type="rss",
        tags=[],
        published_at=datetime(2025, 1, 15),
        fetched_at=datetime(2025, 1, 15),
    )
    defaults.update(kwargs)
    return ContentItem(id=id, url=url, title=title, **defaults)


# --- _build_where ---


class TestBuildWhere:
    """_build_where is a pure string-builder — use a single shared DB instance."""

    @pytest.fixture(scope="class")
    def db(self, tmp_path_factory):
        backend = SqliteBackend(tmp_path_factory.mktemp("build_where") / "test.db")
        yield backend
        backend.close()

    def test_no_filters(self, db):
        where, params = db._build_where()
        assert "is_duplicate_of IS NULL" in where
        assert params == []

    def test_min_score(self, db):
        where, params = db._build_where(min_score=0.5)
        assert "score >= ?" in where
        assert params == [0.5]

    def test_source_type(self, db):
        where, params = db._build_where(source_type="twitter")
        assert "source_type = ?" in where
        assert params == ["twitter"]

    def test_source_types_list(self, db):
        where, params = db._build_where(source_types=["rss", "youtube"])
        assert "source_type IN (?,?)" in where
        assert params == ["rss", "youtube"]

    def test_tier(self, db):
        where, params = db._build_where(tier="work")
        assert "tier = ?" in where
        assert params == ["work"]

    def test_since(self, db):
        dt = datetime(2025, 1, 1)
        where, params = db._build_where(since=dt)
        assert "fetched_at >= ?" in where
        assert params == [dt.isoformat()]

    def test_tag(self, db):
        where, params = db._build_where(tag="ai")
        assert "item_tags" in where
        assert params == ["ai"]

    def test_search(self, db):
        where, params = db._build_where(search="GPT")
        assert "title LIKE ?" in where
        assert params == ["%GPT%", "%GPT%", "%GPT%"]

    def test_source_name(self, db):
        where, params = db._build_where(source_name="Blog")
        assert "source_name = ?" in where
        assert params == ["Blog"]

    def test_exclude_sources(self, db):
        where, params = db._build_where(exclude_sources=["A", "B"])
        assert "source_name NOT IN (?,?)" in where
        assert params == ["A", "B"]

    def test_exclude_source_types(self, db):
        where, params = db._build_where(exclude_source_types=["events"])
        assert "source_type NOT IN (?)" in where
        assert params == ["events"]

    def test_multiple_filters_combined(self, db):
        where, params = db._build_where(min_score=0.3, source_type="rss", tag="ai", search="test")
        assert "score >= ?" in where
        assert "source_type = ?" in where
        assert "item_tags" in where
        assert "title LIKE ?" in where
        assert len(params) == 6  # 0.3, "rss", "ai", "%test%"x3


# --- get_existing_ids chunking ---


class TestGetExistingIds:
    def test_empty_list(self, db):
        assert db.get_existing_ids([]) == set()

    def test_returns_matching_ids(self, db):
        db.upsert_item(_item(id="a", url="https://a.com"))
        db.upsert_item(_item(id="b", url="https://b.com"))
        db.commit()
        result = db.get_existing_ids(["a", "b", "c"])
        assert result == {"a", "b"}

    def test_chunks_large_lists(self, db):
        """IDs are chunked at 900 — verify 1000+ IDs still work."""
        # Insert a few items
        for i in range(5):
            db.upsert_item(_item(id=f"id-{i}", url=f"https://example.com/{i}"))
        db.commit()

        # Query with more than 900 IDs
        query_ids = [f"id-{i}" for i in range(1200)]
        result = db.get_existing_ids(query_ids)
        assert result == {f"id-{i}" for i in range(5)}

    def test_exactly_900_ids(self, db):
        db.upsert_item(_item(id="x", url="https://x.com"))
        db.commit()
        query_ids = ["x"] + [f"other-{i}" for i in range(899)]
        assert len(query_ids) == 900
        result = db.get_existing_ids(query_ids)
        assert result == {"x"}

    def test_901_ids_triggers_second_chunk(self, db):
        """901 is the first count that splits into two chunks (900 + 1)."""
        db.upsert_item(_item(id="first-chunk", url="https://first.com"))
        db.upsert_item(_item(id="second-chunk", url="https://second.com"))
        db.commit()
        # "first-chunk" lands in chunk 1 (indices 0-899), "second-chunk" in chunk 2 (index 900)
        query_ids = ["first-chunk"] + [f"pad-{i}" for i in range(899)] + ["second-chunk"]
        assert len(query_ids) == 901
        result = db.get_existing_ids(query_ids)
        assert result == {"first-chunk", "second-chunk"}


# --- Tag sync ---


class TestTagSync:
    def test_tags_inserted_on_upsert(self, db):
        db.upsert_item(_item(tags=["ai", "ml"]))
        db.commit()
        tags = db.get_all_tags()
        assert "ai" in tags
        assert "ml" in tags

    def test_empty_tags_no_rows(self, db):
        db.upsert_item(_item(tags=[]))
        db.commit()
        assert db.get_all_tags() == []

    def test_duplicate_tags_ignored(self, db):
        db.upsert_item(_item(tags=["ai", "ai"]))
        db.commit()
        assert db.get_all_tags() == ["ai"]


# --- Upsert score preservation ---


class TestUpsertScorePreservation:
    def test_reingest_without_score_preserves_existing(self, db):
        db.upsert_item(_item(score=0.8, score_reason="good", tier="work"))
        db.commit()
        db.upsert_item(_item(score=None, score_reason="", tier=""))
        db.commit()
        items = db.get_items()
        assert items[0].score == 0.8
        assert items[0].score_reason == "good"
        assert items[0].tier == "work"

    def test_new_score_overwrites_old(self, db):
        db.upsert_item(_item(score=0.5, score_reason="ok", tier="personal"))
        db.commit()
        db.upsert_item(_item(score=0.9, score_reason="great", tier="work"))
        db.commit()
        items = db.get_items()
        assert items[0].score == 0.9
        assert items[0].score_reason == "great"


# --- get_items ordering ---


class TestGetItemsOrdering:
    def test_date_order_default(self, db):
        db.upsert_item(_item(id="old", url="https://old.com", published_at=datetime(2025, 1, 1)))
        db.upsert_item(_item(id="new", url="https://new.com", published_at=datetime(2025, 6, 1)))
        db.commit()
        items = db.get_items(order_by="date")
        assert items[0].id == "new"
        assert items[1].id == "old"

    def test_score_order(self, db):
        db.upsert_item(_item(id="low", url="https://low.com", score=0.2))
        db.upsert_item(_item(id="high", url="https://high.com", score=0.9))
        db.commit()
        items = db.get_items(order_by="score")
        assert items[0].id == "high"
        assert items[1].id == "low"

    def test_null_scores_sorted_last(self, db):
        db.upsert_item(_item(id="scored", url="https://scored.com", score=0.5))
        db.upsert_item(_item(id="unscored", url="https://unscored.com", score=None))
        db.commit()
        items = db.get_items(order_by="score")
        assert items[0].id == "scored"


# --- Ingest dedup ---


class TestIngestItems:
    def test_skips_existing(self, db):
        db.upsert_item(_item(id="existing", url="https://existing.com"))
        db.commit()
        items = [
            _item(id="existing", url="https://existing.com"),
            _item(id="new", url="https://new.com"),
        ]
        new_count = db.ingest_items("TestSource", items)
        assert new_count == 1

    def test_sets_last_fetched(self, db):
        db.ingest_items("TestSource", [_item()])
        assert db.get_last_fetched("TestSource") is not None


# --- Delete source content ---


class TestDeleteSourceContent:
    def test_deletes_items_and_tags(self, db):
        db.upsert_item(_item(tags=["ai"]))
        db.commit()
        count = db.delete_source_content("TestSource")
        assert count == 1
        assert db.count_items() == 0
        assert db.get_all_tags() == []

    def test_delete_nonexistent_source(self, db):
        count = db.delete_source_content("NoSuchSource")
        assert count == 0


# --- Count with filters ---


class TestCountItems:
    def test_count_all(self, db):
        db.upsert_item(_item(id="1", url="https://1.com"))
        db.upsert_item(_item(id="2", url="https://2.com"))
        db.commit()
        assert db.count_items() == 2

    def test_count_excludes_duplicates(self, db):
        db.upsert_item(_item(id="1", url="https://1.com"))
        db.upsert_item(_item(id="2", url="https://2.com", is_duplicate_of="1"))
        db.commit()
        assert db.count_items() == 1

    def test_count_with_tag_filter(self, db):
        db.upsert_item(_item(id="1", url="https://1.com", tags=["ai"]))
        db.upsert_item(_item(id="2", url="https://2.com", tags=["sports"]))
        db.commit()
        assert db.count_items(tag="ai") == 1


# --- Delete old items ---


class TestDeleteOldItems:
    def test_deletes_items_before_cutoff(self, db):
        old_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
        new_dt = datetime(2025, 6, 1, tzinfo=timezone.utc)
        db.upsert_item(_item(id="old", url="https://old.com", fetched_at=old_dt))
        db.upsert_item(_item(id="new", url="https://new.com", fetched_at=new_dt))
        db.commit()
        cutoff = datetime(2025, 3, 1, tzinfo=timezone.utc)
        deleted = db.delete_old_items(cutoff)
        assert deleted == 1
        assert db.count_items() == 1
        items = db.get_items()
        assert items[0].id == "new"

    def test_deletes_associated_tags(self, db):
        db.upsert_item(
            _item(
                id="old",
                url="https://old.com",
                tags=["ai", "ml"],
                fetched_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            )
        )
        db.upsert_item(
            _item(
                id="new",
                url="https://new.com",
                tags=["ai"],
                fetched_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            )
        )
        db.commit()
        cutoff = datetime(2025, 3, 1, tzinfo=timezone.utc)
        db.delete_old_items(cutoff)
        tags = db.get_all_tags()
        assert "ai" in tags
        assert "ml" not in tags

    def test_no_items_to_delete(self, db):
        recent_dt = datetime(2025, 6, 1, tzinfo=timezone.utc)
        db.upsert_item(_item(id="recent", url="https://recent.com", fetched_at=recent_dt))
        db.commit()
        cutoff = datetime(2025, 1, 1, tzinfo=timezone.utc)
        deleted = db.delete_old_items(cutoff)
        assert deleted == 0
        assert db.count_items() == 1

    def test_empty_db(self, db):
        cutoff = datetime(2025, 6, 1, tzinfo=timezone.utc)
        deleted = db.delete_old_items(cutoff)
        assert deleted == 0


# --- Delete past events ---


class TestDeletePastEvents:
    def test_deletes_past_events_keeps_future(self, db):
        past = datetime(2025, 1, 1, tzinfo=timezone.utc)
        future = datetime(2025, 12, 1, tzinfo=timezone.utc)
        db.upsert_item(
            _item(id="past_event", url="https://past.com", source_type="events", published_at=past)
        )
        db.upsert_item(
            _item(
                id="future_event",
                url="https://future.com",
                source_type="events",
                published_at=future,
            )
        )
        db.commit()
        cutoff = datetime(2025, 6, 1, tzinfo=timezone.utc)
        deleted = db.delete_past_events(cutoff)
        assert deleted == 1
        items = db.get_items()
        assert len(items) == 1
        assert items[0].id == "future_event"

    def test_deletes_luma_events(self, db):
        past = datetime(2025, 1, 1, tzinfo=timezone.utc)
        db.upsert_item(
            _item(
                id="past_luma",
                url="https://luma.com/past",
                source_type="luma",
                published_at=past,
            )
        )
        db.commit()
        cutoff = datetime(2025, 6, 1, tzinfo=timezone.utc)
        deleted = db.delete_past_events(cutoff)
        assert deleted == 1

    def test_ignores_non_event_items(self, db):
        past = datetime(2025, 1, 1, tzinfo=timezone.utc)
        db.upsert_item(
            _item(id="rss_old", url="https://rss.com/old", source_type="rss", published_at=past)
        )
        db.commit()
        cutoff = datetime(2025, 6, 1, tzinfo=timezone.utc)
        deleted = db.delete_past_events(cutoff)
        assert deleted == 0
        assert db.count_items() == 1

    def test_cleans_up_tags(self, db):
        past = datetime(2025, 1, 1, tzinfo=timezone.utc)
        db.upsert_item(
            _item(
                id="tagged_event",
                url="https://event.com/tagged",
                source_type="events",
                tags=["unique_tag"],
                published_at=past,
            )
        )
        db.commit()
        cutoff = datetime(2025, 6, 1, tzinfo=timezone.utc)
        db.delete_past_events(cutoff)
        assert "unique_tag" not in db.get_all_tags()

    def test_empty_db(self, db):
        cutoff = datetime(2025, 6, 1, tzinfo=timezone.utc)
        deleted = db.delete_past_events(cutoff)
        assert deleted == 0
