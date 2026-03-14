-- Migration: User accounts, RLS, and user_sources table
-- Run this in Supabase SQL Editor AFTER supabase_schema.sql

-- ---------------------------------------------------------------------------
-- 1. Add user_id to existing tables
-- ---------------------------------------------------------------------------

ALTER TABLE items ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);
CREATE INDEX IF NOT EXISTS idx_items_user_id ON items(user_id);

-- Drop legacy URL uniqueness (constraint or index) and add per-user partial indexes
ALTER TABLE items DROP CONSTRAINT IF EXISTS items_url_key;
DROP INDEX IF EXISTS idx_items_url;
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_url_public ON items(url) WHERE user_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_items_url_user_scoped ON items(url, user_id) WHERE user_id IS NOT NULL;

ALTER TABLE source_state ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);

-- Replace single-column PK with two partial unique indexes (same pattern as items).
-- PostgREST ON CONFLICT needs real unique constraints, not composite with NULLs.
ALTER TABLE source_state DROP CONSTRAINT IF EXISTS source_state_pkey;
-- Public mode: unique on source_key alone (user_id is NULL)
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_state_public
    ON source_state(source_key) WHERE user_id IS NULL;
-- Per-user mode: unique on (source_key, user_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_state_user
    ON source_state(source_key, user_id) WHERE user_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. user_sources table — per-user source configuration
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL DEFAULT auth.uid() REFERENCES auth.users(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    name TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags JSONB DEFAULT '[]'::jsonb,
    disabled BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, source_type, name)
);

CREATE INDEX IF NOT EXISTS idx_user_sources_user_id ON user_sources(user_id);

-- ---------------------------------------------------------------------------
-- 3. RLS policies
-- ---------------------------------------------------------------------------

ALTER TABLE items ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_sources ENABLE ROW LEVEL SECURITY;

-- items: users only see their own items (no cross-tenant leakage)
DROP POLICY IF EXISTS items_select ON items;
CREATE POLICY items_select ON items FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS items_insert ON items;
CREATE POLICY items_insert ON items FOR INSERT WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS items_update ON items;
CREATE POLICY items_update ON items FOR UPDATE USING (auth.uid() = user_id);
DROP POLICY IF EXISTS items_delete ON items;
CREATE POLICY items_delete ON items FOR DELETE USING (auth.uid() = user_id);

-- source_state: users only see their own state
DROP POLICY IF EXISTS source_state_select ON source_state;
CREATE POLICY source_state_select ON source_state FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS source_state_insert ON source_state;
CREATE POLICY source_state_insert ON source_state FOR INSERT WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS source_state_update ON source_state;
CREATE POLICY source_state_update ON source_state FOR UPDATE USING (auth.uid() = user_id);
DROP POLICY IF EXISTS source_state_delete ON source_state;
CREATE POLICY source_state_delete ON source_state FOR DELETE USING (auth.uid() = user_id);

-- user_sources: users can only see/modify their own sources
DROP POLICY IF EXISTS user_sources_select ON user_sources;
CREATE POLICY user_sources_select ON user_sources FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS user_sources_insert ON user_sources;
CREATE POLICY user_sources_insert ON user_sources FOR INSERT WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS user_sources_update ON user_sources;
CREATE POLICY user_sources_update ON user_sources FOR UPDATE USING (auth.uid() = user_id);
DROP POLICY IF EXISTS user_sources_delete ON user_sources;
CREATE POLICY user_sources_delete ON user_sources FOR DELETE USING (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- 4. Updated RPC functions (SECURITY DEFINER to work from both anon + service role)
-- ---------------------------------------------------------------------------

-- Upsert item with user_id
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
    p_is_duplicate_of TEXT DEFAULT NULL,
    p_user_id UUID DEFAULT NULL
) RETURNS void AS $$
BEGIN
    -- Validate caller owns the user_id (service role has auth.uid() = NULL, so allow NULL)
    IF p_user_id IS NOT NULL AND auth.uid() IS NOT NULL AND p_user_id != auth.uid() THEN
        RAISE EXCEPTION 'unauthorized: user_id mismatch';
    END IF;

    INSERT INTO items (id, url, title, summary, content, source_name, source_type,
                       tags, author, published_at, fetched_at, score, score_reason,
                       tier, is_duplicate_of, user_id)
    VALUES (p_id, p_url, p_title, p_summary, p_content, p_source_name, p_source_type,
            p_tags, p_author, p_published_at, p_fetched_at, p_score, p_score_reason,
            p_tier, p_is_duplicate_of, p_user_id)
    ON CONFLICT (id) DO UPDATE SET
        score = COALESCE(EXCLUDED.score, items.score),
        score_reason = CASE WHEN EXCLUDED.score_reason IS NOT NULL AND EXCLUDED.score_reason != ''
                            THEN EXCLUDED.score_reason ELSE items.score_reason END,
        tier = CASE WHEN EXCLUDED.tier IS NOT NULL AND EXCLUDED.tier != ''
                    THEN EXCLUDED.tier ELSE items.tier END,
        is_duplicate_of = COALESCE(EXCLUDED.is_duplicate_of, items.is_duplicate_of)
    -- Strict tenant match: IS NOT DISTINCT FROM handles NULL=NULL for public mode
    WHERE items.user_id IS NOT DISTINCT FROM p_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Source health with user_id filter
CREATE OR REPLACE FUNCTION get_source_health(p_user_id UUID DEFAULT NULL)
RETURNS TABLE(source_name TEXT, source_type TEXT, item_count BIGINT, last_fetched TEXT) AS $$
BEGIN
    -- Enforce caller can only query their own data (service role has auth.uid() = NULL)
    IF p_user_id IS NOT NULL AND auth.uid() IS NOT NULL AND p_user_id != auth.uid() THEN
        RAISE EXCEPTION 'unauthorized: user_id mismatch';
    END IF;

    RETURN QUERY
    SELECT i.source_name, i.source_type, COUNT(*)::BIGINT as item_count,
           MAX(i.fetched_at)::TEXT as last_fetched
    FROM items i
    WHERE i.is_duplicate_of IS NULL
      AND (p_user_id IS NULL OR i.user_id = p_user_id)
    GROUP BY i.source_name, i.source_type;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- All tags with user_id filter
CREATE OR REPLACE FUNCTION get_all_tags(p_user_id UUID DEFAULT NULL)
RETURNS TABLE(tag TEXT) AS $$
BEGIN
    -- Enforce caller can only query their own data
    IF p_user_id IS NOT NULL AND auth.uid() IS NOT NULL AND p_user_id != auth.uid() THEN
        RAISE EXCEPTION 'unauthorized: user_id mismatch';
    END IF;

    RETURN QUERY
    SELECT DISTINCT jsonb_array_elements_text(items.tags) as tag
    FROM items
    WHERE (p_user_id IS NULL OR items.user_id = p_user_id)
    ORDER BY tag;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Mark YouTube Shorts duplicates scoped by user_id
CREATE OR REPLACE FUNCTION mark_youtube_shorts_duplicates(p_user_id UUID DEFAULT NULL)
RETURNS integer AS $$
DECLARE
    affected integer;
BEGIN
    -- Enforce caller can only affect their own data
    IF p_user_id IS NOT NULL AND auth.uid() IS NOT NULL AND p_user_id != auth.uid() THEN
        RAISE EXCEPTION 'unauthorized: user_id mismatch';
    END IF;

    UPDATE items SET is_duplicate_of = (
        SELECT f.id FROM items f
        WHERE f.source_name = items.source_name
          AND LOWER(f.title) = LOWER(items.title)
          AND f.url LIKE '%youtube.com/watch?v=%'
          AND (p_user_id IS NULL AND f.user_id IS NULL OR f.user_id = p_user_id)
        LIMIT 1
    )
    WHERE items.url LIKE '%youtube.com/shorts/%'
      AND items.is_duplicate_of IS NULL
      AND (p_user_id IS NULL AND items.user_id IS NULL OR items.user_id = p_user_id)
      AND EXISTS (
          SELECT 1 FROM items f
          WHERE f.source_name = items.source_name
            AND LOWER(f.title) = LOWER(items.title)
            AND f.url LIKE '%youtube.com/watch?v=%'
            AND (p_user_id IS NULL AND f.user_id IS NULL OR f.user_id = p_user_id)
      );
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Upsert source_state (handles partial indexes that PostgREST can't use for ON CONFLICT)
CREATE OR REPLACE FUNCTION upsert_source_state(
    p_source_key TEXT,
    p_last_fetched_at TIMESTAMPTZ DEFAULT now(),
    p_user_id UUID DEFAULT NULL
) RETURNS void AS $$
BEGIN
    IF p_user_id IS NOT NULL AND auth.uid() IS NOT NULL AND p_user_id != auth.uid() THEN
        RAISE EXCEPTION 'unauthorized: user_id mismatch';
    END IF;

    IF p_user_id IS NULL THEN
        INSERT INTO source_state (source_key, last_fetched_at, user_id)
        VALUES (p_source_key, p_last_fetched_at, NULL)
        ON CONFLICT (source_key) WHERE user_id IS NULL
        DO UPDATE SET last_fetched_at = EXCLUDED.last_fetched_at;
    ELSE
        INSERT INTO source_state (source_key, last_fetched_at, user_id)
        VALUES (p_source_key, p_last_fetched_at, p_user_id)
        ON CONFLICT (source_key, user_id) WHERE user_id IS NOT NULL
        DO UPDATE SET last_fetched_at = EXCLUDED.last_fetched_at;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
