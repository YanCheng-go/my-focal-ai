-- Fix RPC auth gap: anon key could upsert items for any user_id (#115)
--
-- The old guard only fired when BOTH auth.uid() and p_user_id were non-NULL.
-- With the anon key (no session), auth.uid() is NULL, so the check was skipped.
-- This migration adds an explicit NULL check: if p_user_id is set, the caller
-- MUST be authenticated (auth.uid() IS NOT NULL) and must match.
-- The service_role is exempted because cloud_fetch_all_users() uses it to
-- write items on behalf of each user.

-- 1. upsert_item
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
    -- Require authentication when writing to a user's feed
    -- Service role (cloud_fetch_all_users) may write on behalf of any user
    IF p_user_id IS NOT NULL
       AND current_setting('request.jwt.claim.role', true) != 'service_role' THEN
        IF auth.uid() IS NULL THEN
            RAISE EXCEPTION 'authentication required';
        END IF;
        IF auth.uid() != p_user_id THEN
            RAISE EXCEPTION 'unauthorized: user_id mismatch';
        END IF;
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
    WHERE items.user_id IS NOT DISTINCT FROM p_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 2. get_source_health
CREATE OR REPLACE FUNCTION get_source_health(p_user_id UUID DEFAULT NULL)
RETURNS TABLE(source_name TEXT, source_type TEXT, item_count BIGINT, last_fetched TEXT) AS $$
BEGIN
    -- Service role (cloud_fetch_all_users) may write on behalf of any user
    IF p_user_id IS NOT NULL
       AND current_setting('request.jwt.claim.role', true) != 'service_role' THEN
        IF auth.uid() IS NULL THEN
            RAISE EXCEPTION 'authentication required';
        END IF;
        IF auth.uid() != p_user_id THEN
            RAISE EXCEPTION 'unauthorized: user_id mismatch';
        END IF;
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

-- 3. get_all_tags
CREATE OR REPLACE FUNCTION get_all_tags(p_user_id UUID DEFAULT NULL)
RETURNS TABLE(tag TEXT) AS $$
BEGIN
    -- Service role (cloud_fetch_all_users) may write on behalf of any user
    IF p_user_id IS NOT NULL
       AND current_setting('request.jwt.claim.role', true) != 'service_role' THEN
        IF auth.uid() IS NULL THEN
            RAISE EXCEPTION 'authentication required';
        END IF;
        IF auth.uid() != p_user_id THEN
            RAISE EXCEPTION 'unauthorized: user_id mismatch';
        END IF;
    END IF;

    RETURN QUERY
    SELECT DISTINCT jsonb_array_elements_text(items.tags) as tag
    FROM items
    WHERE (p_user_id IS NULL OR items.user_id = p_user_id)
    ORDER BY tag;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 4. mark_youtube_shorts_duplicates
CREATE OR REPLACE FUNCTION mark_youtube_shorts_duplicates(p_user_id UUID DEFAULT NULL)
RETURNS integer AS $$
DECLARE
    affected integer;
BEGIN
    -- Service role (cloud_fetch_all_users) may write on behalf of any user
    IF p_user_id IS NOT NULL
       AND current_setting('request.jwt.claim.role', true) != 'service_role' THEN
        IF auth.uid() IS NULL THEN
            RAISE EXCEPTION 'authentication required';
        END IF;
        IF auth.uid() != p_user_id THEN
            RAISE EXCEPTION 'unauthorized: user_id mismatch';
        END IF;
    END IF;

    UPDATE items SET is_duplicate_of = (
        SELECT f.id FROM items f
        WHERE f.source_name = items.source_name
          AND LOWER(f.title) = LOWER(items.title)
          AND f.url LIKE '%youtube.com/watch?v=%'
          AND f.user_id IS NOT DISTINCT FROM p_user_id
        LIMIT 1
    )
    WHERE items.url LIKE '%youtube.com/shorts/%'
      AND items.is_duplicate_of IS NULL
      AND items.user_id IS NOT DISTINCT FROM p_user_id
      AND EXISTS (
          SELECT 1 FROM items f
          WHERE f.source_name = items.source_name
            AND LOWER(f.title) = LOWER(items.title)
            AND f.url LIKE '%youtube.com/watch?v=%'
            AND f.user_id IS NOT DISTINCT FROM p_user_id
      );
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 5. upsert_source_state
CREATE OR REPLACE FUNCTION upsert_source_state(
    p_source_key TEXT,
    p_last_fetched_at TIMESTAMPTZ DEFAULT now(),
    p_user_id UUID DEFAULT NULL
) RETURNS void AS $$
BEGIN
    -- Service role (cloud_fetch_all_users) may write on behalf of any user
    IF p_user_id IS NOT NULL
       AND current_setting('request.jwt.claim.role', true) != 'service_role' THEN
        IF auth.uid() IS NULL THEN
            RAISE EXCEPTION 'authentication required';
        END IF;
        IF auth.uid() != p_user_id THEN
            RAISE EXCEPTION 'unauthorized: user_id mismatch';
        END IF;
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
