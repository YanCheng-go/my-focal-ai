"""SQLite storage for content items."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ainews.models import ContentItem


def get_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection):
    conn.executescript("""
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


def _sync_tags(conn: sqlite3.Connection, item_id: str, tags: list[str]):
    """Insert tags into the item_tags junction table."""
    if tags:
        conn.executemany(
            "INSERT OR IGNORE INTO item_tags (item_id, tag) VALUES (?, ?)",
            [(item_id, tag) for tag in tags],
        )


def get_last_fetched(conn: sqlite3.Connection, source_key: str) -> datetime | None:
    row = conn.execute(
        "SELECT last_fetched_at FROM source_state WHERE source_key = ?", (source_key,)
    ).fetchone()
    if row:
        return datetime.fromisoformat(row["last_fetched_at"])
    return None


def set_last_fetched(conn: sqlite3.Connection, source_key: str, ts: datetime | None = None):
    """Update last_fetched_at for a source. Does NOT commit — caller must commit."""
    ts = ts or datetime.now()
    conn.execute(
        """INSERT INTO source_state (source_key, last_fetched_at) VALUES (?, ?)
           ON CONFLICT(source_key) DO UPDATE SET last_fetched_at = excluded.last_fetched_at""",
        (source_key, ts.isoformat()),
    )


def mark_youtube_shorts_duplicates(conn: sqlite3.Connection) -> int:
    """Mark YouTube Shorts as duplicates when a full video exists."""
    cursor = conn.execute("""
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
    conn.commit()
    return cursor.rowcount


def get_existing_ids(conn: sqlite3.Connection, item_ids: list[str]) -> set[str]:
    """Batch-check which item IDs already exist in the DB."""
    if not item_ids:
        return set()
    result: set[str] = set()
    # Chunk to stay under SQLite's SQLITE_MAX_VARIABLE_NUMBER (default 999)
    for i in range(0, len(item_ids), 900):
        chunk = item_ids[i : i + 900]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(f"SELECT id FROM items WHERE id IN ({placeholders})", chunk).fetchall()
        result.update(row["id"] for row in rows)
    return result


def upsert_item(conn: sqlite3.Connection, item: ContentItem):
    """Insert or update a single item. Does NOT commit — caller must commit."""
    conn.execute(
        """INSERT INTO items (id, url, title, summary, content, source_name, source_type,
           tags, author, published_at, fetched_at, score, score_reason, tier, is_duplicate_of)
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
    _sync_tags(conn, item.id, item.tags)


def ingest_items(conn: sqlite3.Connection, source_key: str, items: list[ContentItem]) -> int:
    """Upsert new items and update last_fetched. Returns new count."""
    existing = get_existing_ids(conn, [i.id for i in items])
    new_count = 0
    for item in items:
        if item.id not in existing:
            upsert_item(conn, item)
            new_count += 1
    set_last_fetched(conn, source_key)
    conn.commit()
    return new_count


def get_source_health(conn: sqlite3.Connection) -> dict[str, dict]:
    """Get item counts and last fetch time per source."""
    rows = conn.execute("""
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
    # Also include source_state for last run times
    state_rows = conn.execute("SELECT source_key, last_fetched_at FROM source_state").fetchall()
    for row in state_rows:
        key = row["source_key"]
        if key not in health:
            health[key] = {"source_type": "", "item_count": 0, "last_fetched": None}
        health[key]["last_run"] = row["last_fetched_at"]
    return health


def _build_where(
    *,
    min_score: float | None = None,
    source_type: str | None = None,
    tier: str | None = None,
    since: datetime | None = None,
    tag: str | None = None,
    search: str | None = None,
    exclude_sources: list[str] | None = None,
    exclude_source_types: list[str] | None = None,
    source_types: list[str] | None = None,
) -> tuple[str, list]:
    """Build WHERE clause and params for item queries."""
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
    conn: sqlite3.Connection,
    *,
    min_score: float | None = None,
    source_type: str | None = None,
    tier: str | None = None,
    since: datetime | None = None,
    tag: str | None = None,
    search: str | None = None,
    exclude_sources: list[str] | None = None,
    exclude_source_types: list[str] | None = None,
    source_types: list[str] | None = None,
) -> int:
    where, params = _build_where(
        min_score=min_score,
        source_type=source_type,
        tier=tier,
        since=since,
        tag=tag,
        search=search,
        exclude_sources=exclude_sources,
        exclude_source_types=exclude_source_types,
        source_types=source_types,
    )
    row = conn.execute(f"SELECT count(*) as c FROM items {where}", params).fetchone()
    return row["c"]


def get_all_tags(conn: sqlite3.Connection) -> list[str]:
    """Get all unique tags from the item_tags index table."""
    rows = conn.execute("SELECT DISTINCT tag FROM item_tags ORDER BY tag").fetchall()
    return [row["tag"] for row in rows]


def get_items(
    conn: sqlite3.Connection,
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
    where, params = _build_where(
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
        query = (
            f"SELECT items.* FROM items {where}"
            " ORDER BY items.score DESC NULLS LAST,"
            " items.published_at DESC, items.fetched_at DESC"
        )
    else:
        # Sort by published_at, but push events (luma) to the bottom
        query = f"""SELECT items.* FROM items {where}
            ORDER BY CASE WHEN items.source_type = 'luma' THEN 1 ELSE 0 END,
                     items.published_at DESC NULLS LAST, items.fetched_at DESC"""

    query += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    return [_row_to_item(r) for r in rows]


def get_unscored_items(conn: sqlite3.Connection, limit: int = 50) -> list[ContentItem]:
    rows = conn.execute(
        "SELECT * FROM items WHERE score IS NULL ORDER BY fetched_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_item(r) for r in rows]


def _row_to_item(row: sqlite3.Row) -> ContentItem:
    d = dict(row)
    d["tags"] = json.loads(d["tags"])
    if d["published_at"]:
        d["published_at"] = datetime.fromisoformat(d["published_at"])
    d["fetched_at"] = datetime.fromisoformat(d["fetched_at"])
    return ContentItem(**d)
