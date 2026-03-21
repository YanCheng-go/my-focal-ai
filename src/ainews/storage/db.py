"""SQLite storage backend for content items."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ainews.models import ContentItem


class SqliteBackend:
    """SQLite implementation of the DbBackend protocol."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                summary TEXT DEFAULT '',
                content TEXT DEFAULT '',
                source_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                author TEXT DEFAULT '',
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                score REAL,
                score_reason TEXT DEFAULT '',
                tier TEXT DEFAULT '',
                is_duplicate_of TEXT,
                FOREIGN KEY (is_duplicate_of) REFERENCES items(id)
            );
            CREATE INDEX IF NOT EXISTS idx_items_score ON items(score DESC);
            CREATE INDEX IF NOT EXISTS idx_items_fetched ON items(fetched_at DESC);
            CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_type);
            CREATE TABLE IF NOT EXISTS source_state (
                source_key TEXT PRIMARY KEY,
                last_fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS item_tags (
                item_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (item_id, tag),
                FOREIGN KEY (item_id) REFERENCES items(id)
            );
            CREATE INDEX IF NOT EXISTS idx_item_tags_tag ON item_tags(tag);
        """)

    def close(self) -> None:
        self._conn.close()

    def commit(self) -> None:
        self._conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def _sync_tags(self, item_id: str, tags: list[str]):
        if tags:
            self._conn.executemany(
                "INSERT OR IGNORE INTO item_tags (item_id, tag) VALUES (?, ?)",
                [(item_id, tag) for tag in tags],
            )

    def get_last_fetched(self, source_key: str) -> datetime | None:
        row = self._conn.execute(
            "SELECT last_fetched_at FROM source_state WHERE source_key = ?", (source_key,)
        ).fetchone()
        if row:
            return datetime.fromisoformat(row["last_fetched_at"])
        return None

    def set_last_fetched(self, source_key: str, ts: datetime | None = None) -> None:
        ts = ts or datetime.now(timezone.utc)
        self._conn.execute(
            """INSERT INTO source_state (source_key, last_fetched_at) VALUES (?, ?)
               ON CONFLICT(source_key) DO UPDATE SET last_fetched_at = excluded.last_fetched_at""",
            (source_key, ts.isoformat()),
        )

    def mark_youtube_shorts_duplicates(self) -> int:
        cursor = self._conn.execute("""
            UPDATE items SET is_duplicate_of = (
                SELECT f.id FROM items f
                WHERE f.source_name = items.source_name
                  AND LOWER(f.title) = LOWER(items.title)
                  AND f.url LIKE '%youtube.com/watch?v=%'
                LIMIT 1
            )
            WHERE items.url LIKE '%youtube.com/shorts/%'
              AND items.is_duplicate_of IS NULL
              AND EXISTS (
                  SELECT 1 FROM items f
                  WHERE f.source_name = items.source_name
                    AND LOWER(f.title) = LOWER(items.title)
                    AND f.url LIKE '%youtube.com/watch?v=%'
              )
        """)
        self._conn.commit()
        return cursor.rowcount

    def get_existing_ids(self, item_ids: list[str]) -> set[str]:
        if not item_ids:
            return set()
        result: set[str] = set()
        for i in range(0, len(item_ids), 900):
            chunk = item_ids[i : i + 900]
            placeholders = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                f"SELECT id FROM items WHERE id IN ({placeholders})", chunk
            ).fetchall()
            result.update(row["id"] for row in rows)
        return result

    def upsert_item(self, item: ContentItem) -> None:
        try:
            self._conn.execute(
                """INSERT INTO items (id, url, title, summary, content,
                   source_name, source_type, tags, author, published_at,
                   fetched_at, score, score_reason, tier, is_duplicate_of)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     score=COALESCE(excluded.score, items.score),
                     score_reason=CASE WHEN excluded.score_reason IS NOT NULL
                                       AND excluded.score_reason != ''
                                       THEN excluded.score_reason ELSE items.score_reason END,
                     tier=CASE WHEN excluded.tier IS NOT NULL AND excluded.tier != ''
                               THEN excluded.tier ELSE items.tier END,
                     is_duplicate_of=COALESCE(excluded.is_duplicate_of, items.is_duplicate_of)
                """,
                (
                    item.id,
                    item.url,
                    item.title,
                    item.summary,
                    item.content,
                    item.source_name,
                    item.source_type,
                    json.dumps(item.tags),
                    item.author,
                    item.published_at.isoformat() if item.published_at else None,
                    item.fetched_at.isoformat(),
                    item.score,
                    item.score_reason,
                    item.tier,
                    item.is_duplicate_of,
                ),
            )
        except sqlite3.IntegrityError:
            # Different id but duplicate URL — skip silently
            return
        self._sync_tags(item.id, item.tags)

    def ingest_items(self, source_key: str, items: list[ContentItem]) -> int:
        existing = self.get_existing_ids([i.id for i in items])
        new_count = 0
        for item in items:
            if item.id not in existing:
                self.upsert_item(item)
                new_count += 1
        self.set_last_fetched(source_key)
        self._conn.commit()
        return new_count

    def get_source_health(self) -> dict[str, dict]:
        rows = self._conn.execute("""
            SELECT source_name, source_type, COUNT(*) as item_count,
                   MAX(fetched_at) as last_fetched
            FROM items WHERE is_duplicate_of IS NULL
            GROUP BY source_name
        """).fetchall()
        health = {}
        for row in rows:
            health[row["source_name"]] = {
                "source_type": row["source_type"],
                "item_count": row["item_count"],
                "last_fetched": row["last_fetched"],
            }
        state_rows = self._conn.execute(
            "SELECT source_key, last_fetched_at FROM source_state"
        ).fetchall()
        for row in state_rows:
            key = row["source_key"]
            if key not in health:
                health[key] = {"source_type": "", "item_count": 0, "last_fetched": None}
            health[key]["last_run"] = row["last_fetched_at"]
        return health

    def _build_where(
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
    ) -> tuple[str, list]:
        where = "WHERE items.is_duplicate_of IS NULL"
        params: list = []

        if min_score is not None:
            where += " AND items.score >= ?"
            params.append(min_score)
        if source_type:
            where += " AND items.source_type = ?"
            params.append(source_type)
        if source_types:
            placeholders = ",".join("?" for _ in source_types)
            where += f" AND items.source_type IN ({placeholders})"
            params.extend(source_types)
        if tier:
            where += " AND items.tier = ?"
            params.append(tier)
        if since:
            where += " AND items.fetched_at >= ?"
            params.append(since.isoformat())
        if tag:
            where += " AND items.id IN (SELECT item_id FROM item_tags WHERE tag = ?)"
            params.append(tag)
        if source_name:
            where += " AND items.source_name = ?"
            params.append(source_name)
        if search:
            where += " AND (items.title LIKE ? OR items.summary LIKE ? OR items.source_name LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term])
        if exclude_sources:
            placeholders = ",".join("?" for _ in exclude_sources)
            where += f" AND items.source_name NOT IN ({placeholders})"
            params.extend(exclude_sources)
        if exclude_source_types:
            placeholders = ",".join("?" for _ in exclude_source_types)
            where += f" AND items.source_type NOT IN ({placeholders})"
            params.extend(exclude_source_types)

        return where, params

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
        where, params = self._build_where(
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
        row = self._conn.execute(f"SELECT count(*) as c FROM items {where}", params).fetchone()
        return row["c"]

    def count_items_by_source_type(
        self,
        *,
        since: datetime,
        exclude_sources: list[str] | None = None,
        exclude_source_types: list[str] | None = None,
    ) -> dict[str, int]:
        where = "WHERE is_duplicate_of IS NULL AND fetched_at >= ?"
        params: list = [since.isoformat()]
        if exclude_sources:
            placeholders = ",".join("?" for _ in exclude_sources)
            where += f" AND source_name NOT IN ({placeholders})"
            params.extend(exclude_sources)
        if exclude_source_types:
            placeholders = ",".join("?" for _ in exclude_source_types)
            where += f" AND source_type NOT IN ({placeholders})"
            params.extend(exclude_source_types)
        rows = self._conn.execute(
            f"SELECT source_type, COUNT(*) as c FROM items {where} GROUP BY source_type",
            params,
        ).fetchall()
        return {row["source_type"]: row["c"] for row in rows}

    def get_all_tags(self) -> list[str]:
        rows = self._conn.execute("SELECT DISTINCT tag FROM item_tags ORDER BY tag").fetchall()
        return [row["tag"] for row in rows]

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
    ) -> list[ContentItem]:
        where, params = self._build_where(
            min_score=min_score,
            source_type=source_type,
            tier=tier,
            since=since,
            tag=tag,
            search=search,
            source_name=source_name,
            source_types=source_types,
            exclude_sources=exclude_sources,
            exclude_source_types=exclude_source_types,
        )

        if order_by == "score":
            query = (
                f"SELECT items.* FROM items {where}"
                " ORDER BY items.score DESC NULLS LAST,"
                " items.published_at DESC, items.fetched_at DESC"
            )
        else:
            query = f"""SELECT items.* FROM items {where}
                ORDER BY CASE WHEN items.source_type = 'luma' THEN 1 ELSE 0 END,
                         items.published_at DESC NULLS LAST, items.fetched_at DESC"""

        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(query, params).fetchall()
        return [_row_to_item(r) for r in rows]

    def get_unscored_items(self, limit: int = 50) -> list[ContentItem]:
        rows = self._conn.execute(
            "SELECT * FROM items WHERE score IS NULL ORDER BY fetched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_item(r) for r in rows]

    def delete_source_content(self, source_name: str) -> int:
        self._conn.execute(
            "DELETE FROM item_tags WHERE item_id IN (SELECT id FROM items WHERE source_name = ?)",
            (source_name,),
        )
        cursor = self._conn.execute("DELETE FROM items WHERE source_name = ?", (source_name,))
        self._conn.execute("DELETE FROM source_state WHERE source_key = ?", (source_name,))
        self._conn.commit()
        return cursor.rowcount

    def get_items_for_backfill(self) -> list[dict]:
        rows = self._conn.execute("SELECT id, source_name, source_type, tags FROM items").fetchall()
        return [dict(row) for row in rows]

    def update_item_metadata(self, item_id: str, tags: list[str], source_type: str) -> None:
        self._conn.execute(
            "UPDATE items SET tags = ?, source_type = ? WHERE id = ?",
            (json.dumps(tags), source_type, item_id),
        )
        self._conn.execute("DELETE FROM item_tags WHERE item_id = ?", (item_id,))
        if tags:
            self._conn.executemany(
                "INSERT OR IGNORE INTO item_tags (item_id, tag) VALUES (?, ?)",
                [(item_id, tag) for tag in tags],
            )

    def get_stored_hash(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT last_fetched_at FROM source_state WHERE source_key = ?",
            (key,),
        ).fetchone()
        return row["last_fetched_at"] if row else None

    def store_hash(self, key: str, hash_val: str) -> None:
        self._conn.execute(
            """INSERT INTO source_state (source_key, last_fetched_at) VALUES (?, ?)
               ON CONFLICT(source_key) DO UPDATE SET last_fetched_at = excluded.last_fetched_at""",
            (key, hash_val),
        )

    def delete_old_items(self, before: datetime) -> int:
        cutoff = before.isoformat()
        self._conn.execute(
            "DELETE FROM item_tags WHERE item_id IN "
            "(SELECT id FROM items WHERE fetched_at < ?)",
            (cutoff,),
        )
        cursor = self._conn.execute("DELETE FROM items WHERE fetched_at < ?", (cutoff,))
        self._conn.commit()
        return cursor.rowcount


def _row_to_item(row) -> ContentItem:
    d = dict(row)
    d["tags"] = json.loads(d["tags"])
    if d["published_at"]:
        dt = datetime.fromisoformat(d["published_at"])
        # Treat pre-migration naive timestamps as UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        d["published_at"] = dt
    dt = datetime.fromisoformat(d["fetched_at"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    d["fetched_at"] = dt
    return ContentItem(**d)


def get_backend(db_path: Path | None = None, user_id: str | None = None):
    """Factory — returns the appropriate backend based on config.

    When db_path is explicitly provided, always uses SQLite (local mode).
    When only Supabase env vars are set (no db_path), uses SupabaseBackend.
    """
    from ainews.config import Settings

    settings = Settings()

    if db_path is None and settings.supabase_url and settings.supabase_key:
        from ainews.storage.supabase_backend import SupabaseBackend

        key = settings.supabase_service_key or settings.supabase_key
        return SupabaseBackend(settings.supabase_url, key, user_id=user_id)

    return SqliteBackend(db_path or settings.db_path)
