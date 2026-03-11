# Spike: Cloud Database Migration -- Turso (libSQL) vs Supabase (Postgres)

**Date:** 2026-03-11
**Status:** Complete
**Decision:** Use Turso with embedded replicas. Minimal migration effort due to SQLite-compatible API, and the free tier is generous enough for this project indefinitely.

## Question

Should the project migrate from local SQLite to a cloud database, and if so, which service -- Turso (libSQL/SQLite-compatible) or Supabase (Postgres) -- is the better fit?

## Context

The project currently uses SQLite in WAL mode via Python's `sqlite3` module. All database logic lives in `src/ainews/storage/db.py` (351 lines, ~15 functions). The app has two modes:

1. **Local**: FastAPI + SQLite file on disk. Single user, ~5000 items, 2-hour fetch cycles.
2. **Cloud**: GitHub Actions fetches feeds, exports to `static/data.json`, deployed to Vercel as a static site.

The cloud mode cannot query the database at request time -- it relies on a JSON export. A cloud database would enable dynamic queries from the Vercel static site (or a future serverless API), eliminating the export step and enabling features like real-time search and filtering.

## Current SQLite Usage Analysis

Key SQLite-specific features used in `db.py`:

| Feature | Location | Migration Impact |
|---------|----------|-----------------|
| `sqlite3.connect()` | `get_db()` L13 | Connection setup |
| `sqlite3.Row` row_factory | `get_db()` L14 | Dict-like row access used everywhere |
| `PRAGMA journal_mode=WAL` | `get_db()` L15 | SQLite-specific optimization |
| `conn.executescript()` | `_init_schema()` L21 | Multi-statement DDL |
| `conn.execute()` direct | Throughout | Shorthand (no explicit cursor) |
| `cursor.rowcount` | `mark_youtube_shorts_duplicates()` L107 | Update count |
| `INSERT OR IGNORE` | `_sync_tags()` L63 | SQLite upsert syntax |
| `ON CONFLICT(...) DO UPDATE` | `upsert_item()` L130, `set_last_fetched()` L81 | Standard upsert |
| `COALESCE` in upsert | `upsert_item()` L131 | Preserve existing scores |
| `LIKE` for search | `_build_where()` L238 | Case-insensitive by default in SQLite |
| `NULLS LAST` in ORDER BY | `get_items()` L321, L327 | Sort control |
| Chunked `IN (?)` queries | `get_existing_ids()` L116 | SQLite 999-variable limit |
| `f"SELECT ... IN ({placeholders})"` | `_build_where()` L222-248 | Dynamic SQL building |
| Type annotations: `sqlite3.Connection` | All function signatures | Type hints |

Functions that pass `sqlite3.Connection` as a parameter: `_init_schema`, `_sync_tags`, `get_last_fetched`, `set_last_fetched`, `mark_youtube_shorts_duplicates`, `get_existing_ids`, `upsert_item`, `ingest_items`, `get_source_health`, `count_items`, `get_all_tags`, `get_items`, `get_unscored_items`. Additionally, `sqlite3.Connection` is used as type annotation in `twitter.py` and `xiaohongshu.py`.

## Options Evaluated

### Option A: Turso (libSQL) with Embedded Replicas

**How it works:** Turso is a managed edge database built on libSQL, an open-source fork of SQLite. The Python SDK (`pip install libsql`) provides an API modeled after Python's `sqlite3` module: `libsql.connect()`, `conn.execute()`, `conn.cursor()`, `conn.commit()`. "Embedded replicas" mode keeps a local SQLite file that syncs to/from Turso's cloud, giving you local-speed reads with cloud persistence.

**Migration effort for db.py:**

```python
# BEFORE (current)
import sqlite3
conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

# AFTER (Turso - local only, no cloud sync)
import libsql
conn = libsql.connect(str(db_path))

# AFTER (Turso - embedded replica with cloud sync)
import libsql
conn = libsql.connect(
    str(db_path),
    sync_url=os.getenv("TURSO_DATABASE_URL"),
    auth_token=os.getenv("TURSO_AUTH_TOKEN"),
)
conn.sync()
```

Functions requiring changes:

| Function | Change needed |
|----------|--------------|
| `get_db()` | Replace `sqlite3.connect` with `libsql.connect`, add sync_url/auth_token params. Remove `row_factory` (see below). |
| `_init_schema()` | `executescript()` -- **unknown if supported**. May need to split into individual `execute()` calls. |
| `_row_to_item()` | Currently relies on `sqlite3.Row` dict-like access (`row["field"]`). Needs workaround. |
| All type hints | Change `sqlite3.Connection` to the libsql equivalent (or use a Protocol). |
| `mark_youtube_shorts_duplicates()` | Verify `cursor.rowcount` works. |
| All other functions | SQL syntax is identical -- no changes to queries. |

**Critical gap: `row_factory` is NOT yet supported** in Turso's Python SDK (as of March 2026). There is an [open feature request](https://github.com/tursodatabase/turso/discussions/4276) from December 2025. This means `row["field"]` dict-style access would not work. Workaround: write a helper to convert tuples to dicts using `cursor.description`, or wait for the feature.

**Workaround for row_factory:**

```python
def _dict_row(cursor, row):
    """Drop-in replacement for sqlite3.Row until libsql adds row_factory."""
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}

# Would need to wrap all fetchall/fetchone calls, or create a connection wrapper
```

**Pros:**
- SQL is 100% SQLite-compatible -- all existing queries work unchanged
- Embedded replica mode: local file for fast reads, cloud sync for persistence
- Can run purely local (no cloud) during development -- same code path
- Free tier: 500M row reads/month, 5GB storage -- vastly exceeds project needs (~5K items)
- No project pausing on inactivity
- Data export: the local replica IS a SQLite file -- trivially exportable
- Incremental migration: start local-only, add cloud sync later via env vars

**Cons:**
- Python SDK is less mature than sqlite3 (no `row_factory`, unclear `executescript` support)
- SDK is ~1 year old; fewer community resources and Stack Overflow answers
- Need to handle `conn.sync()` calls for embedded replica mode
- Adding a new dependency (`libsql`) where `sqlite3` is in the stdlib

**Effort:** Small (s) -- mostly connection setup + row_factory workaround. All SQL unchanged.
**Risk:** Medium -- SDK maturity is the main concern. `row_factory` gap requires workaround code.

### Option B: Supabase (Postgres)

**How it works:** Supabase provides a managed Postgres database with a REST API (PostgREST) and client libraries. The Python SDK (`supabase-py`) uses a query-builder pattern, not raw SQL. For complex queries, you must create Postgres functions (RPC) and call them via `supabase.rpc()`.

**Migration effort for db.py:**

This would be a **complete rewrite**. The supabase-py SDK does not support raw SQL execution. Every function would need to be converted from SQL to the query-builder API or wrapped in Postgres functions.

```python
# BEFORE (current)
rows = conn.execute(
    "SELECT * FROM items WHERE score IS NULL ORDER BY fetched_at DESC LIMIT ?",
    (limit,),
).fetchall()

# AFTER (Supabase query builder)
response = (
    supabase.table("items")
    .select("*")
    .is_("score", "null")
    .order("fetched_at", desc=True)
    .limit(limit)
    .execute()
)
rows = response.data
```

Functions requiring changes:

| Function | Change needed |
|----------|--------------|
| `get_db()` | Complete rewrite: `create_client(url, key)` instead of file path |
| `_init_schema()` | Must run DDL via Supabase dashboard or migration tool, not from Python |
| `_sync_tags()` | Rewrite to `.upsert()` with `ignore_duplicates=True` |
| `get_last_fetched()` | Rewrite to `.select().eq().execute()` |
| `set_last_fetched()` | Rewrite to `.upsert()` with `on_conflict` |
| `mark_youtube_shorts_duplicates()` | **Requires a Postgres function (RPC)** -- correlated subquery UPDATE is too complex for the query builder |
| `get_existing_ids()` | Rewrite to `.select("id").in_("id", chunk)` -- no 999-var limit in Postgres |
| `upsert_item()` | Rewrite to `.upsert()` -- but COALESCE-based partial update logic requires a Postgres function |
| `ingest_items()` | Rewrite orchestration around new API |
| `get_source_health()` | **Requires a Postgres function** -- GROUP BY with aggregates |
| `_build_where()` | Complete rewrite to chain `.eq()`, `.gte()`, `.like()`, `.in_()`, `.not_in()` etc. |
| `count_items()` | Rewrite with `.select("*", count="exact")` |
| `get_all_tags()` | Rewrite to `.select("tag").execute()` |
| `get_items()` | Rewrite with query builder + conditional ordering (CASE WHEN requires RPC) |
| `get_unscored_items()` | Rewrite to query builder |
| `_row_to_item()` | Simpler -- Supabase returns dicts. But date parsing changes. |
| All callers | Connection object changes from `sqlite3.Connection` to `supabase.Client` |
| `twitter.py`, `xiaohongshu.py` | Update type annotations and `ingest_items` calls |
| Tests | Complete rewrite -- cannot use tmp_path SQLite files |

Additionally, 3-4 Postgres functions would need to be created and maintained in the Supabase dashboard (or via a migration tool) for:
- `mark_youtube_shorts_duplicates` (correlated UPDATE)
- `upsert_item` with COALESCE logic
- `get_source_health` (GROUP BY aggregation)
- `get_items` with CASE WHEN ordering

**Pros:**
- Postgres is a mature, well-understood database
- supabase-py is actively maintained with good documentation
- Built-in auth, realtime subscriptions, and storage (not needed now, but available)
- Row Level Security for future multi-user scenarios
- PostgREST API means the static site could query directly (no export step)

**Cons:**
- **Complete rewrite of db.py** -- every function changes, not just connection setup
- **3-4 Postgres functions** needed for complex queries (maintained outside Python code)
- supabase-py does NOT support raw SQL -- forces query-builder or RPC pattern
- Free tier pauses projects after 7 days of inactivity (requires keep-alive workaround)
- Free tier: 500MB storage, 2 projects only
- `LIKE` behaves differently in Postgres (case-sensitive by default; need `ILIKE`)
- `NULLS LAST` syntax differs in some contexts
- Cannot run locally without a Supabase instance (or a separate local Postgres)
- Tests become integration tests requiring a database connection
- Two-mode problem: local dev would need either a Supabase project or a separate code path

**Effort:** Large (l) -- full rewrite of db.py (~350 lines), plus Postgres function creation, schema migration, test rewrite.
**Risk:** High -- large surface area for bugs, loss of local-only development mode, vendor lock-in to Supabase's query builder API.

### Option C: Keep SQLite + Enhance Export

**How it works:** Keep the current architecture. Improve the static export (`data.json`) to support more filtering, or add a lightweight serverless API (e.g., Vercel Serverless Functions reading from a SQLite file stored in object storage or bundled with the deployment).

**Pros:**
- Zero migration effort
- SQLite is the right tool for a single-user, ~5K item dataset
- No new dependencies or services
- Local development stays simple
- Could add Litestream for SQLite replication to S3 if backup is needed

**Cons:**
- No dynamic queries from the static site (current limitation persists)
- Export step remains in the pipeline

**Effort:** Extra-small (xs) for status quo, small (s) if adding Litestream backup.
**Risk:** Low.

## Recommendation

**Option A (Turso) is recommended if cloud database access is needed, but Option C (keep SQLite) is the pragmatic choice for now.**

Rationale:

1. **The project's scale does not require a cloud database.** With ~5000 items, a single user, and 2-hour fetch cycles, SQLite is the correct database. The export-to-JSON pipeline works. Adding a cloud database solves a problem (dynamic queries from Vercel) that can be addressed more simply.

2. **If/when a cloud database becomes necessary**, Turso is clearly the better choice over Supabase for this project:
   - Migration effort is ~20 lines changed in `db.py` vs ~350 lines rewritten for Supabase
   - All SQL queries work unchanged with Turso
   - Embedded replica mode preserves local-first development
   - Free tier is more generous and does not pause on inactivity
   - No vendor lock-in to a proprietary query builder

3. **The main blocker for Turso today is the Python SDK's missing `row_factory` support.** The project uses `sqlite3.Row` extensively for dict-like row access. Until this ships, migration requires either a wrapper or converting all `row["field"]` access to tuple indexing -- doable but adds friction.

4. **Supabase is not a good fit** for this project. It would require rewriting every database function, creating Postgres stored procedures for complex queries, adding keep-alive hacks to prevent free-tier pausing, and losing the ability to develop locally without a cloud service. The benefits (auth, realtime, RLS) are irrelevant for a single-user personal tool.

**Recommended timeline:**
- **Now:** Stay on SQLite. No action needed.
- **When Turso's Python SDK adds `row_factory`:** Re-evaluate. Migration would then be ~30 minutes of work.
- **If dynamic queries from Vercel become a priority:** Migrate to Turso with embedded replicas. The GitHub Actions cloud-fetch workflow would write to Turso instead of exporting JSON.

## Next Steps

- [ ] Monitor [Turso Python SDK row_factory discussion](https://github.com/tursodatabase/turso/discussions/4276) for resolution
- [ ] If dynamic Vercel queries become a priority, create a backlog item for Turso migration
- [ ] Consider adding Litestream (SQLite replication to S3) as a simpler backup solution before committing to a cloud database
- [ ] No changes to `db.py` needed at this time

## References

- [Turso Pricing](https://turso.tech/pricing) -- free tier: 5GB storage, 500M reads/month, 100 databases
- [Turso Python SDK Quickstart](https://docs.turso.tech/sdk/python/quickstart) -- installation and connection examples
- [libsql-python GitHub](https://github.com/tursodatabase/libsql-python) -- Python bindings source, 238 commits, actively maintained
- [Turso row_factory discussion](https://github.com/tursodatabase/turso/discussions/4276) -- open feature request from Dec 2025
- [Supabase Pricing](https://supabase.com/pricing) -- free tier: 500MB, 2 projects, pauses after 7 days
- [Supabase Python Upsert Docs](https://supabase.com/docs/reference/python/upsert) -- query builder API reference
- [Supabase raw SQL discussion](https://github.com/orgs/supabase/discussions/11797) -- confirms no raw SQL support in client SDK
- [Supabase pause prevention](https://github.com/travisvn/supabase-pause-prevention) -- community workaround for free-tier inactivity pausing

*Last updated: 2026-03-11*
