"""Supabase (Postgres) implementation of the DbBackend protocol."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from ainews.models import ContentItem

logger = logging.getLogger(__name__)

try:
    from supabase import create_client
except ImportError:  # pragma: no cover
    create_client = None  # type: ignore[assignment]


class SupabaseBackend:
    """Supabase implementation of the DbBackend protocol.

    Uses the supabase-py client (REST/PostgREST). Each operation auto-commits —
    commit() and close() are no-ops for compatibility with the protocol.
    """

    def __init__(self, url: str, key: str, user_id: str | None = None):
        if create_client is None:
            raise ImportError("supabase package required. Install with: uv sync --extra supabase")
        self._client = create_client(url, key)
        self._user_id = user_id

    def close(self) -> None:
        pass  # No persistent connection to close

    def commit(self) -> None:
        pass  # Auto-commit per operation

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def get_last_fetched(self, source_key: str) -> datetime | None:
        q = (
            self._client.table("source_state")
            .select("last_fetched_at")
            .eq("source_key", source_key)
        )
        if self._user_id:
            q = q.eq("user_id", self._user_id)
        result = q.execute()
        if result.data:
            return datetime.fromisoformat(result.data[0]["last_fetched_at"])
        return None

    def set_last_fetched(self, source_key: str, ts: datetime | None = None) -> None:
        ts = ts or datetime.now()
        row = {"source_key": source_key, "last_fetched_at": ts.isoformat()}
        if self._user_id:
            row["user_id"] = self._user_id
        self._client.table("source_state").upsert(
            row,
            on_conflict="source_key" if not self._user_id else "source_key,user_id",
        ).execute()

    def mark_youtube_shorts_duplicates(self) -> int:
        # Use RPC for complex UPDATE with subquery, scoped by user_id
        params = {}
        if self._user_id:
            params["p_user_id"] = self._user_id
        result = self._client.rpc("mark_youtube_shorts_duplicates", params).execute()
        return result.data if isinstance(result.data, int) else 0

    def get_existing_ids(self, item_ids: list[str]) -> set[str]:
        if not item_ids:
            return set()
        result: set[str] = set()
        # PostgREST `in` filter has URL length limits; chunk like SQLite
        for i in range(0, len(item_ids), 500):
            chunk = item_ids[i : i + 500]
            q = self._client.table("items").select("id").in_("id", chunk)
            if self._user_id:
                q = q.eq("user_id", self._user_id)
            resp = q.execute()
            result.update(row["id"] for row in resp.data)
        return result

    def upsert_item(self, item: ContentItem) -> None:
        row = {
            "p_id": item.id,
            "p_url": item.url,
            "p_title": item.title,
            "p_summary": item.summary,
            "p_content": item.content,
            "p_source_name": item.source_name,
            "p_source_type": item.source_type,
            "p_tags": item.tags,  # Postgres stores as jsonb natively
            "p_author": item.author,
            "p_published_at": item.published_at.isoformat() if item.published_at else None,
            "p_fetched_at": item.fetched_at.isoformat(),
            "p_score": item.score,
            "p_score_reason": item.score_reason,
            "p_tier": item.tier,
            "p_is_duplicate_of": item.is_duplicate_of,
            "p_user_id": self._user_id,
        }
        # Use RPC for COALESCE upsert logic (preserve existing scores)
        self._client.rpc("upsert_item", row).execute()

    def ingest_items(self, source_key: str, items: list[ContentItem]) -> int:
        existing = self.get_existing_ids([i.id for i in items])
        new_count = 0
        for item in items:
            if item.id not in existing:
                self.upsert_item(item)
                new_count += 1
        self.set_last_fetched(source_key)
        return new_count

    def get_source_health(self) -> dict[str, dict]:
        params = {}
        if self._user_id:
            params["p_user_id"] = self._user_id
        result = self._client.rpc("get_source_health", params).execute()
        health: dict[str, dict] = {}
        for row in result.data or []:
            health[row["source_name"]] = {
                "source_type": row["source_type"],
                "item_count": row["item_count"],
                "last_fetched": row["last_fetched"],
            }
        # Also include source_state for last run times
        q = self._client.table("source_state").select("*")
        if self._user_id:
            q = q.eq("user_id", self._user_id)
        state = q.execute()
        for row in state.data or []:
            key = row["source_key"]
            if key not in health:
                health[key] = {"source_type": "", "item_count": 0, "last_fetched": None}
            health[key]["last_run"] = row["last_fetched_at"]
        return health

    def _build_query(
        self,
        *,
        count_only: bool = False,
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
    ):
        """Build a PostgREST query with filters."""
        if count_only:
            q = self._client.table("items").select("*", count="exact")
        else:
            q = self._client.table("items").select("*")

        q = q.is_("is_duplicate_of", "null")

        if self._user_id:
            q = q.eq("user_id", self._user_id)

        if min_score is not None:
            q = q.gte("score", min_score)
        if source_type:
            q = q.eq("source_type", source_type)
        if source_types:
            q = q.in_("source_type", source_types)
        if tier:
            q = q.eq("tier", tier)
        if since:
            q = q.gte("fetched_at", since.isoformat())
        if tag:
            # Postgres jsonb array containment: tags @> '["tag"]'
            q = q.contains("tags", [tag])
        if source_name:
            q = q.eq("source_name", source_name)
        if search:
            # Escape special PostgREST filter characters to prevent injection
            safe = search.replace("\\", "\\\\").replace("%", "\\%")
            safe = safe.replace(",", "").replace(".", " ")
            q = q.or_(f"title.ilike.%{safe}%,summary.ilike.%{safe}%,source_name.ilike.%{safe}%")
        if exclude_sources:
            for src in exclude_sources:
                q = q.neq("source_name", src)
        if exclude_source_types:
            for st in exclude_source_types:
                q = q.neq("source_type", st)

        return q

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
    ) -> int:
        q = self._build_query(
            count_only=True,
            min_score=min_score,
            source_type=source_type,
            tier=tier,
            since=since,
            tag=tag,
            search=search,
            source_name=source_name,
            exclude_sources=exclude_sources,
            exclude_source_types=exclude_source_types,
            source_types=source_types,
        )
        result = q.execute()
        return result.count or 0

    def get_all_tags(self) -> list[str]:
        params = {}
        if self._user_id:
            params["p_user_id"] = self._user_id
        result = self._client.rpc("get_all_tags", params).execute()
        return [row["tag"] for row in result.data or []]

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
        order_by: str = "date",
        exclude_sources: list[str] | None = None,
        exclude_source_types: list[str] | None = None,
        source_types: list[str] | None = None,
    ) -> list[ContentItem]:
        q = self._build_query(
            min_score=min_score,
            source_type=source_type,
            tier=tier,
            since=since,
            tag=tag,
            search=search,
            source_types=source_types,
            exclude_sources=exclude_sources,
            exclude_source_types=exclude_source_types,
        )

        if order_by == "score":
            q = q.order("score", desc=True, nullsfirst=False)
            q = q.order("published_at", desc=True, nullsfirst=False)
            q = q.order("fetched_at", desc=True)
        else:
            # Default: date order, push luma events to bottom
            # PostgREST doesn't support CASE in ORDER BY, so we use RPC or
            # accept slight difference: order by published_at desc
            q = q.order("published_at", desc=True, nullsfirst=False)
            q = q.order("fetched_at", desc=True)

        q = q.range(offset, offset + limit - 1)
        result = q.execute()
        return [_row_to_item(row) for row in result.data or []]

    def get_unscored_items(self, limit: int = 50) -> list[ContentItem]:
        q = self._client.table("items").select("*").is_("score", "null")
        if self._user_id:
            q = q.eq("user_id", self._user_id)
        result = q.order("fetched_at", desc=True).limit(limit).execute()
        return [_row_to_item(row) for row in result.data or []]

    def delete_source_content(self, source_name: str) -> int:
        # Count before delete (PostgREST DELETE doesn't return count reliably)
        q = self._client.table("items").select("*", count="exact").eq("source_name", source_name)
        if self._user_id:
            q = q.eq("user_id", self._user_id)
        count_result = q.execute()
        deleted = count_result.count or 0

        # Delete items
        dq = self._client.table("items").delete().eq("source_name", source_name)
        if self._user_id:
            dq = dq.eq("user_id", self._user_id)
        dq.execute()
        sq = self._client.table("source_state").delete().eq("source_key", source_name)
        if self._user_id:
            sq = sq.eq("user_id", self._user_id)
        sq.execute()
        return deleted

    def get_items_for_backfill(self) -> list[dict]:
        q = self._client.table("items").select("id, source_name, source_type, tags")
        if self._user_id:
            q = q.eq("user_id", self._user_id)
        result = q.execute()
        return result.data or []

    def update_item_metadata(self, item_id: str, tags: list[str], source_type: str) -> None:
        q = (
            self._client.table("items")
            .update({"tags": tags, "source_type": source_type})
            .eq("id", item_id)
        )
        if self._user_id:
            q = q.eq("user_id", self._user_id)
        q.execute()

    def get_stored_hash(self, key: str) -> str | None:
        q = self._client.table("source_state").select("last_fetched_at").eq("source_key", key)
        if self._user_id:
            q = q.eq("user_id", self._user_id)
        result = q.execute()
        if result.data:
            return result.data[0]["last_fetched_at"]
        return None

    def store_hash(self, key: str, hash_val: str) -> None:
        row = {"source_key": key, "last_fetched_at": hash_val}
        if self._user_id:
            row["user_id"] = self._user_id
        self._client.table("source_state").upsert(
            row,
            on_conflict="source_key" if not self._user_id else "source_key,user_id",
        ).execute()


def _row_to_item(row: dict) -> ContentItem:
    """Convert a Supabase row dict to ContentItem."""
    d = dict(row)
    # Supabase returns tags as native JSON array (not a string)
    if isinstance(d.get("tags"), str):
        d["tags"] = json.loads(d["tags"])
    if d.get("published_at") and isinstance(d["published_at"], str):
        d["published_at"] = datetime.fromisoformat(d["published_at"])
    if isinstance(d.get("fetched_at"), str):
        d["fetched_at"] = datetime.fromisoformat(d["fetched_at"])
    return ContentItem(**d)
