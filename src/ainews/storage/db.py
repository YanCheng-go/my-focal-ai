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
    """)


def get_last_fetched(conn: sqlite3.Connection, source_key: str) -> datetime | None:
    row = conn.execute(
        "SELECT last_fetched_at FROM source_state WHERE source_key = ?", (source_key,)
    ).fetchone()
    if row:
        return datetime.fromisoformat(row["last_fetched_at"])
    return None


def set_last_fetched(conn: sqlite3.Connection, source_key: str, ts: datetime | None = None):
    ts = ts or datetime.now()
    conn.execute(
        """INSERT INTO source_state (source_key, last_fetched_at) VALUES (?, ?)
           ON CONFLICT(source_key) DO UPDATE SET last_fetched_at = excluded.last_fetched_at""",
        (source_key, ts.isoformat()),
    )
    conn.commit()


def mark_youtube_shorts_duplicates(conn: sqlite3.Connection) -> int:
    """Mark YouTube Shorts as duplicates when a full video with the same title exists from the same source."""
    # Find shorts that have a matching full video
    rows = conn.execute("""
        SELECT s.id as short_id, f.id as full_id
        FROM items s
        JOIN items f ON f.source_name = s.source_name
                    AND LOWER(f.title) = LOWER(s.title)
                    AND f.url LIKE '%youtube.com/watch?v=%'
        WHERE s.url LIKE '%youtube.com/shorts/%'
          AND s.is_duplicate_of IS NULL
    """).fetchall()
    for row in rows:
        conn.execute("UPDATE items SET is_duplicate_of = ? WHERE id = ?",
                     (row["full_id"], row["short_id"]))
    conn.commit()
    return len(rows)


def item_exists(conn: sqlite3.Connection, item_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone()
    return row is not None


def upsert_item(conn: sqlite3.Connection, item: ContentItem):
    conn.execute(
        """INSERT INTO items (id, url, title, summary, content, source_name, source_type,
           tags, author, published_at, fetched_at, score, score_reason, tier, is_duplicate_of)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             score=COALESCE(excluded.score, items.score),
             score_reason=COALESCE(excluded.score_reason, items.score_reason),
             tier=COALESCE(excluded.tier, items.tier),
             is_duplicate_of=COALESCE(excluded.is_duplicate_of, items.is_duplicate_of)
        """,
        (
            item.id, item.url, item.title, item.summary, item.content,
            item.source_name, item.source_type, json.dumps(item.tags),
            item.author, item.published_at.isoformat() if item.published_at else None,
            item.fetched_at.isoformat(), item.score, item.score_reason,
            item.tier, item.is_duplicate_of,
        ),
    )
    conn.commit()


def _build_where(
    *,
    min_score: float | None = None,
    source_type: str | None = None,
    tier: str | None = None,
    since: datetime | None = None,
    tag: str | None = None,
    search: str | None = None,
) -> tuple[str, list]:
    """Build WHERE clause and params for item queries."""
    where = "WHERE is_duplicate_of IS NULL"
    params: list = []

    if min_score is not None:
        where += " AND score >= ?"
        params.append(min_score)
    if source_type:
        where += " AND source_type = ?"
        params.append(source_type)
    if tier:
        where += " AND tier = ?"
        params.append(tier)
    if since:
        where += " AND fetched_at >= ?"
        params.append(since.isoformat())
    if tag:
        where += " AND tags LIKE ?"
        params.append(f'%"{tag}"%')
    if search:
        where += " AND (title LIKE ? OR summary LIKE ? OR source_name LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])

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
) -> int:
    where, params = _build_where(
        min_score=min_score, source_type=source_type, tier=tier,
        since=since, tag=tag, search=search,
    )
    row = conn.execute(f"SELECT count(*) as c FROM items {where}", params).fetchone()
    return row["c"]


def get_all_tags(conn: sqlite3.Connection) -> list[str]:
    """Get all unique tags from items."""
    rows = conn.execute("SELECT DISTINCT tags FROM items WHERE is_duplicate_of IS NULL").fetchall()
    tag_set: set[str] = set()
    for row in rows:
        for t in json.loads(row["tags"]):
            tag_set.add(t)
    return sorted(tag_set)


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
) -> list[ContentItem]:
    where, params = _build_where(
        min_score=min_score, source_type=source_type, tier=tier,
        since=since, tag=tag, search=search,
    )

    if order_by == "score":
        query = f"SELECT * FROM items {where} ORDER BY score DESC NULLS LAST, published_at DESC, fetched_at DESC"
    else:
        # Sort by published_at, but push events (luma) to the bottom
        query = f"""SELECT * FROM items {where}
            ORDER BY CASE WHEN source_type = 'luma' THEN 1 ELSE 0 END,
                     published_at DESC NULLS LAST, fetched_at DESC"""

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
