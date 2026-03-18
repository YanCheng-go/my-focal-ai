# Spike: New/Unread Item State Architecture

**Date:** 2026-03-15
**Status:** Complete
**Decision:** Keep localStorage timestamp approach for public/local modes; add a `user_last_seen` table in Supabase for cross-device sync in login mode. Defer per-item read tracking until a clear use case demands it.

## Question

How should MyFocalAI track "new" vs "seen" item state across its three deployment modes? The current localStorage-based approach works but has limitations around cross-device sync, pagination interaction, and cleanup. Should we move to server-side state, per-item tracking, or a hybrid?

## Context

The current implementation (shipped in v0.3.0) uses `localStorage` with per-page timestamps:

- `badges.js` stores `ainews_last_seen_<page>` (one per page: dashboard, trends, ccc)
- On page load, items with `published_at > last_seen` get a blue highlight (`bg-blue-50/70`)
- The timestamp updates to "now" on each visit, clearing highlights on next load
- Badge counts in the nav show how many new items exist per page

This works for the single-device, single-browser case. But users have asked about:
1. State not syncing when they switch between phone and laptop
2. Highlights disappearing instantly on refresh (no "mark as read" control)
3. What happens when paginating back and forth

## Industry Patterns Surveyed

| System | Read State Model | Storage | Cross-Device |
|--------|-----------------|---------|-------------|
| **Miniflux** | Per-entry `status` column (unread/read/removed) | PostgreSQL, per-user rows | Yes (server-side) |
| **FreshRSS** | `is_read` boolean on entry table | Per-user table prefix | Yes (server-side) |
| **Feedly** | Per-entry markers via `/v3/markers` API | Server-side | Yes |
| **Gmail** | Per-message labels (`UNREAD`), thread-level aggregation | Server-side | Yes |
| **Slack** | Cursor-based: `conversations.mark(ts)` stores last-read message timestamp | Server-side, broadcast to all connections | Yes |
| **Twitter/X** | Client-side "Show N new posts" bar; fetches new tweets every ~10s | Mostly client-side, server-augmented | Partially (each client tracks independently) |

**Key insight**: Professional multi-device apps (Miniflux, Gmail, Slack) all use server-side state. Single-device/casual apps (Twitter web, many static sites) use client-side timestamps. The **cursor/timestamp approach** (Slack) and the **per-item boolean approach** (Miniflux, FreshRSS, Gmail) represent two ends of the complexity spectrum.

## Options Evaluated

### Option A: Keep localStorage timestamps (status quo, improved)

**How it works:** Current approach with bug fixes and cleanup. Per-page timestamps in localStorage, `isNewItem()` check during rendering. Add TTL cleanup and pagination-awareness.

Improvements to make:
- Do not update `last_seen` timestamp on page load; update it only when user explicitly clicks a "Mark all as read" button or after a configurable delay (e.g., 30s on page)
- Add cleanup: on each page load, remove any `ainews_last_seen_*` keys older than 90 days
- Pagination fix: capture the cutoff timestamp once when the page first loads; do not recapture when paginating (the current code already does this correctly -- `_lastSeenCutoff` is set in `_compute` before the timestamp updates)

```javascript
// Cleanup: remove stale keys (called on page load)
function _cleanupOldKeys() {
    var cutoff = Date.now() - 90 * 24 * 60 * 60 * 1000;
    for (var i = localStorage.length - 1; i >= 0; i--) {
        var key = localStorage.key(i);
        if (key && key.startsWith('ainews_last_seen_')) {
            var ts = new Date(localStorage.getItem(key)).getTime();
            if (ts < cutoff) localStorage.removeItem(key);
        }
    }
}
```

**Pros:**
- Zero backend changes needed
- Works for all three deployment modes identically
- No database migration or new tables
- Already tested (`test_badges.html` covers the core logic)

**Cons:**
- No cross-device sync: phone and laptop have independent state
- localStorage limit is 5MB per origin (more than enough for timestamps, but grows if we add per-item tracking)
- Users cannot "keep" an item highlighted after refresh without manual "mark as unread"
- Supabase login users get the same dumb-client behavior as anonymous users

**Effort:** xs (a few hours of refinements)
**Risk:** low

### Option B: Hybrid -- localStorage for public, Supabase `user_last_seen` for logged-in

**How it works:** For anonymous/public users, keep localStorage timestamps (Option A). For logged-in Supabase users, store the same per-page timestamps in a `user_last_seen` table. On page load, read from Supabase; on "mark as read" (or timed auto-update), write back.

```sql
-- New table (added to user_accounts migration)
CREATE TABLE IF NOT EXISTS user_last_seen (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    page_key TEXT NOT NULL,  -- 'dashboard', 'trends', 'ccc'
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, page_key)
);

ALTER TABLE user_last_seen ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_last_seen_select ON user_last_seen
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY user_last_seen_upsert ON user_last_seen
    FOR ALL USING (auth.uid() = user_id);
```

Client-side integration in `badges.js`:

```javascript
// When Supabase session exists, read/write server-side
async function _getLastSeen(sb, userId, page) {
    var { data } = await sb.from('user_last_seen')
        .select('last_seen_at')
        .eq('user_id', userId)
        .eq('page_key', page)
        .single();
    return data ? new Date(data.last_seen_at) : null;
}

async function _setLastSeen(sb, userId, page) {
    await sb.from('user_last_seen').upsert({
        user_id: userId,
        page_key: page,
        last_seen_at: new Date().toISOString()
    });
}
```

**Pros:**
- Cross-device sync for logged-in users (the main pain point)
- Minimal schema change (one small table, ~20 lines of SQL)
- Falls back gracefully to localStorage for anonymous users
- Follows the Slack "cursor" pattern -- one timestamp per context, not per item
- Tiny storage footprint: 1 row per user per page (max ~3 rows per user)

**Cons:**
- Adds 1 Supabase query on page load for logged-in users (latency ~50-100ms)
- Need to handle race conditions if user has two tabs open (last write wins is acceptable)
- badges.js grows in complexity (async path for Supabase, sync path for localStorage)
- Still timestamp-based, not per-item -- same "all or nothing" semantics

**Effort:** s (1-2 days: migration, badges.js changes, testing)
**Risk:** low

### Option C: Per-item read tracking via `read_items` table

**How it works:** Full per-item read/unread tracking, like Miniflux or Gmail. A `read_items` table with `(user_id, item_id)` pairs. Items not in the table are unread.

```sql
CREATE TABLE IF NOT EXISTS read_items (
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, item_id)
);
CREATE INDEX idx_read_items_user ON read_items(user_id);
```

Query pattern to get unread items:

```sql
SELECT i.* FROM items i
LEFT JOIN read_items r ON r.item_id = i.id AND r.user_id = $1
WHERE r.item_id IS NULL
  AND i.user_id = $1
ORDER BY i.published_at DESC
LIMIT 30;
```

**Pros:**
- Most flexible: "mark as read", "mark as unread", "show only unread" filter
- Matches user expectations from email/RSS readers
- Enables accurate unread counts in nav badges
- Can coexist with timestamp approach (use timestamp for initial "new" highlight, per-item for persistent read state)

**Cons:**
- Significant storage growth: if a user has 5,000 items, potentially 5,000 rows in `read_items`
- N+1 risk: must JOIN or batch-check read state when rendering items (mitigated by the LEFT JOIN above)
- "Mark all as read" becomes `INSERT INTO read_items SELECT ...` for potentially thousands of items (expensive)
- Client must send read markers as user scrolls or clicks -- more JS complexity
- Not useful for public mode (no user identity) or local mode (single user, less need)
- Supabase free tier row limits become a concern at scale (500K rows total across all tables)

**Effort:** m-l (3-5 days: migration, backend protocol changes, client-side scroll tracking, testing)
**Risk:** medium (performance concerns with large item sets, Supabase row limits)

### Option D: Per-item read tracking in IndexedDB (client-side only)

**How it works:** Store a Set of read item IDs in IndexedDB on the client. No server-side changes. Check each rendered item against the local store.

```javascript
// IndexedDB store: { id: item_id, readAt: timestamp }
async function markAsRead(itemId) {
    const db = await openDB('ainews', 1, { upgrade(db) {
        db.createObjectStore('readItems', { keyPath: 'id' });
    }});
    await db.put('readItems', { id: itemId, readAt: Date.now() });
}

async function getReadIds(itemIds) {
    const db = await openDB('ainews', 1);
    const tx = db.transaction('readItems', 'readonly');
    const store = tx.objectStore('readItems');
    const result = new Set();
    for (const id of itemIds) {
        if (await store.get(id)) result.add(id);
    }
    return result;
}
```

**Pros:**
- No backend changes at all
- Per-item granularity without server cost
- IndexedDB can handle 50MB+ easily, far beyond localStorage 5MB limit
- TTL cleanup is straightforward (delete entries older than 30 days)

**Cons:**
- No cross-device sync (same fundamental problem as localStorage)
- Adds IndexedDB dependency and async complexity to rendering path
- Harder to test (IndexedDB is async, requires browser environment)
- Not compatible with the static data.json public mode (item IDs may shift between exports)

**Effort:** s-m (2-3 days)
**Risk:** low-medium (IndexedDB API complexity, no sync benefit)

## Recommendation

**Option B (Hybrid: localStorage + Supabase `user_last_seen`)** is the right choice for the current project phase.

**Rationale:**

1. **Cross-device sync is the real pain point.** The timestamp approach is fundamentally sound -- it matches what Twitter does and is how most casual content feeds work. The main gap is that logged-in users expect their "seen" state to follow them across devices. Option B solves exactly this.

2. **Per-item tracking is overkill right now.** MyFocalAI is a news aggregator, not an email client. Users scan headlines, not read every item. The RSS reader pattern (Miniflux-style per-item boolean) makes sense when users methodically process every item. For a scored news feed, the timestamp cursor is the right granularity: "Show me what is new since I last looked."

3. **The effort/reward ratio is best for Option B.** One small migration, a few lines of JS, and the most-requested feature (cross-device sync) is solved. Option C would take 3-5x the effort for a feature that most users of a news aggregator do not need.

4. **Option A improvements should be done regardless.** The cleanup logic and delayed timestamp update are good hygiene that apply to all modes. These can land in the same PR as Option B.

**Trade-offs accepted:**
- Anonymous/public users still get localStorage-only state (acceptable -- they have no identity to sync against)
- "Mark individual items as read" is not supported (acceptable for now -- defer to a future spike if users request it)
- Two tabs open on different devices will use "last write wins" for the timestamp (acceptable -- the window is small and the consequence is minor: some items may briefly re-highlight)

## Pagination Interaction (Answering Research Question 5)

The current implementation already handles this correctly. In `badges.js`, `_lastSeenCutoff` is captured once during `_compute()` before the timestamp is updated. As the user navigates pages, the cutoff date remains stable for that session. Items on page 2 that are newer than the cutoff will still be highlighted when the user navigates back to page 1.

The only nuance: in Supabase mode, `computeBadges` is not called (server-side pagination). The `isNewItem()` function is still available but the cutoff must be initialized from the Supabase `user_last_seen` table rather than localStorage. This integration point needs to be handled in the Option B implementation.

## Data Cleanup (Answering Research Question 6)

localStorage cleanup is trivial because we store at most 3-5 keys total (one per page). The concern about unbounded growth does not apply to the timestamp approach. If we were storing per-item read state in localStorage, cleanup would matter -- but that is why per-item tracking belongs in IndexedDB or a database, not localStorage.

For the Supabase `user_last_seen` table, rows are automatically cleaned up via `ON DELETE CASCADE` when a user account is deleted. No TTL is needed because the table stores at most ~3 rows per user.

## Next Steps

- [ ] Add `user_last_seen` table to Supabase migration (Option B schema above)
- [ ] Update `badges.js` to read/write `user_last_seen` when Supabase session is active
- [ ] Add delayed timestamp update: update `last_seen` after 30s on page, or on explicit "Mark all read" button
- [ ] Add localStorage cleanup function for stale keys (defensive, even though growth is minimal)
- [ ] Add `isNewItem()` integration for Supabase mode in `index.html` (currently skipped when `isSupabaseMode` is true)
- [ ] Create GitHub Issue for future consideration: per-item read tracking (Option C) if users request "mark as read" on individual items

## References

- [Miniflux v2 (GitHub)](https://github.com/miniflux/v2) -- Go + PostgreSQL RSS reader with per-entry status column (unread/read/removed)
- [FreshRSS Database Schema (DeepWiki)](https://deepwiki.com/FreshRSS/FreshRSS/5.1-database-schema) -- `is_read` boolean on per-user entry tables
- [Slack conversations.mark API](https://docs.slack.dev/reference/methods/conversations.mark/) -- cursor-based read position using message timestamps, throttled updates
- [Feedly API Reference](https://developers.feedly.com/reference/introduction) -- per-entry read markers via `/v3/markers` endpoint
- [IndexedDB Best Practices for App State (web.dev)](https://web.dev/articles/indexeddb-best-practices-app-state) -- stale-while-revalidate pattern for persisting UI state
- [localStorage in Modern Applications (RxDB)](https://rxdb.info/articles/localstorage.html) -- comprehensive guide on localStorage limits and alternatives

*Last updated: 2026-03-15*
