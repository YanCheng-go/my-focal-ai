-- Supabase schema for ai-news-filter
-- Run this in your Supabase SQL Editor to set up the database.

-- Items table (mirrors SQLite schema)
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT DEFAULT '',
    content TEXT DEFAULT '',
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    tags JSONB DEFAULT '[]'::jsonb,
    author TEXT DEFAULT '',
    published_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ NOT NULL,
    score DOUBLE PRECISION,
    score_reason TEXT DEFAULT '',
    tier TEXT DEFAULT '',
    is_duplicate_of TEXT REFERENCES items(id)
);

CREATE INDEX IF NOT EXISTS idx_items_score ON items(score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_items_fetched ON items(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_type);
CREATE INDEX IF NOT EXISTS idx_items_source_name ON items(source_name);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_items_tags ON items USING gin(tags);

-- URL uniqueness for base schema (single-tenant, no user_id yet).
-- Migration 002 replaces this with partial indexes for multi-tenant support.
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_url ON items(url);

-- Source state table
CREATE TABLE IF NOT EXISTS source_state (
    source_key TEXT PRIMARY KEY,
    last_fetched_at TEXT NOT NULL
);

-- Note: item_tags table is NOT needed for Supabase — tags are stored as
-- native JSONB arrays in the items table and queried with @> containment.

-- ---------------------------------------------------------------------------
-- RPC functions (called from SupabaseBackend)
-- ---------------------------------------------------------------------------

-- Upsert an item, preserving existing scores (COALESCE logic from SQLite)
CREATE OR REPLACE FUNCTION upsert_item(
    p_id TEXT,
    p_url TEXT,
    p_title TEXT,
    p_summary TEXT DEFAULT '',
    p_content TEXT DEFAULT '',
    p_source_name TEXT DEFAULT '',
    p_source_type TEXT DEFAULT '',
    p_tags JSONB DEFAULT '[]'::jsonb,
    p_author TEXT DEFAULT '',
    p_published_at TIMESTAMPTZ DEFAULT NULL,
    p_fetched_at TIMESTAMPTZ DEFAULT now(),
    p_score DOUBLE PRECISION DEFAULT NULL,
    p_score_reason TEXT DEFAULT '',
    p_tier TEXT DEFAULT '',
    p_is_duplicate_of TEXT DEFAULT NULL
) RETURNS void AS $$
BEGIN
    INSERT INTO items (id, url, title, summary, content, source_name, source_type,
                       tags, author, published_at, fetched_at, score, score_reason, tier, is_duplicate_of)
    VALUES (p_id, p_url, p_title, p_summary, p_content, p_source_name, p_source_type,
            p_tags, p_author, p_published_at, p_fetched_at, p_score, p_score_reason, p_tier, p_is_duplicate_of)
    ON CONFLICT (id) DO UPDATE SET
        score = COALESCE(EXCLUDED.score, items.score),
        score_reason = CASE WHEN EXCLUDED.score_reason IS NOT NULL AND EXCLUDED.score_reason != ''
                            THEN EXCLUDED.score_reason ELSE items.score_reason END,
        tier = CASE WHEN EXCLUDED.tier IS NOT NULL AND EXCLUDED.tier != ''
                    THEN EXCLUDED.tier ELSE items.tier END,
        is_duplicate_of = COALESCE(EXCLUDED.is_duplicate_of, items.is_duplicate_of);
END;
$$ LANGUAGE plpgsql;

-- Mark YouTube Shorts as duplicates when a full video exists
CREATE OR REPLACE FUNCTION mark_youtube_shorts_duplicates()
RETURNS integer AS $$
DECLARE
    affected integer;
BEGIN
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
      );
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$ LANGUAGE plpgsql;

-- Get source health stats
CREATE OR REPLACE FUNCTION get_source_health()
RETURNS TABLE(source_name TEXT, source_type TEXT, item_count BIGINT, last_fetched TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT i.source_name, i.source_type, COUNT(*)::BIGINT as item_count,
           MAX(i.fetched_at)::TEXT as last_fetched
    FROM items i
    WHERE i.is_duplicate_of IS NULL
    GROUP BY i.source_name, i.source_type;
END;
$$ LANGUAGE plpgsql;

-- Get all unique tags from jsonb arrays
CREATE OR REPLACE FUNCTION get_all_tags()
RETURNS TABLE(tag TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT jsonb_array_elements_text(items.tags) as tag
    FROM items
    ORDER BY tag;
END;
$$ LANGUAGE plpgsql;
