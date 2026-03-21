"""Database backend protocol — abstraction over SQLite / Supabase."""

from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import Protocol

from ainews.models import ContentItem


class DbBackend(Protocol):
    """Protocol for database backends.

    All storage callers use this interface. Concrete implementations:
    - SqliteBackend (src/ainews/storage/db.py) — local SQLite
    - SupabaseBackend (src/ainews/storage/supabase_backend.py) — Supabase Postgres

    Supports use as a context manager for safe resource cleanup.
    """

    def close(self) -> None: ...

    def commit(self) -> None: ...

    def __enter__(self) -> DbBackend: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...

    def get_last_fetched(self, source_key: str) -> datetime | None: ...

    def set_last_fetched(self, source_key: str, ts: datetime | None = None) -> None: ...

    def mark_youtube_shorts_duplicates(self) -> int: ...

    def get_existing_ids(self, item_ids: list[str]) -> set[str]: ...

    def upsert_item(self, item: ContentItem) -> None: ...

    def ingest_items(self, source_key: str, items: list[ContentItem]) -> int: ...

    def get_source_health(self) -> dict[str, dict]: ...

    def count_items(
        self,
        *,
        min_score: float | None = None,
        source_type: str | None = None,
        tier: str | None = None,
        since: datetime | None = None,
        tag: str | None = None,
        search: str | None = None,
        source_name: str | None = None,
        exclude_sources: list[str] | None = None,
        exclude_source_types: list[str] | None = None,
        source_types: list[str] | None = None,
    ) -> int: ...

    def count_items_by_source_type(
        self,
        *,
        since: datetime,
        exclude_sources: list[str] | None = None,
        exclude_source_types: list[str] | None = None,
    ) -> dict[str, int]: ...

    def get_all_tags(self) -> list[str]: ...

    def get_items(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        min_score: float | None = None,
        source_type: str | None = None,
        tier: str | None = None,
        since: datetime | None = None,
        tag: str | None = None,
        search: str | None = None,
        source_name: str | None = None,
        order_by: str = "date",
        exclude_sources: list[str] | None = None,
        exclude_source_types: list[str] | None = None,
        source_types: list[str] | None = None,
    ) -> list[ContentItem]: ...

    def get_unscored_items(self, limit: int = 50) -> list[ContentItem]: ...

    def delete_source_content(self, source_name: str) -> int:
        """Delete all items, tags, and state for a source. Returns deleted count."""
        ...

    def get_items_for_backfill(self) -> list[dict]:
        """Return id, source_name, source_type, tags for all items."""
        ...

    def update_item_metadata(self, item_id: str, tags: list[str], source_type: str) -> None:
        """Update tags and source_type for a single item."""
        ...

    def get_stored_hash(self, key: str) -> str | None:
        """Get a stored hash value from source_state."""
        ...

    def store_hash(self, key: str, hash_val: str) -> None:
        """Store a hash value in source_state."""
        ...

    def delete_old_items(self, before: datetime) -> int:
        """Delete items older than the given datetime. Returns deleted count."""
        ...
