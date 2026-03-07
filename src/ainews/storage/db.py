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
    """)


def upsert_item(conn: sqlite3.Connection, item: ContentItem):
    conn.execute(
        """INSERT INTO items (id, url, title, summary, content, source_name, source_type,
           tags, author, published_at, fetched_at, score, score_reason, tier, is_duplicate_of)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             score=excluded.score,
             score_reason=excluded.score_reason,
             tier=excluded.tier,
             is_duplicate_of=excluded.is_duplicate_of
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
    order_by: str = "date",
) -> list[ContentItem]:
    query = "SELECT * FROM items WHERE is_duplicate_of IS NULL"
    params: list = []

    if min_score is not None:
        query += " AND score >= ?"
        params.append(min_score)
    if source_type:
        query += " AND source_type = ?"
        params.append(source_type)
    if tier:
        query += " AND tier = ?"
        params.append(tier)
    if since:
        query += " AND fetched_at >= ?"
        params.append(since.isoformat())
    if tag:
        query += " AND tags LIKE ?"
        params.append(f'%"{tag}"%')

    if order_by == "score":
        query += " ORDER BY score DESC NULLS LAST, fetched_at DESC"
    else:
        query += " ORDER BY published_at DESC NULLS LAST, fetched_at DESC"

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
