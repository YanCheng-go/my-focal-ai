# Architecture

## Overview

MyFocalAI follows a linear pipeline: **ingest -> dedup -> store -> score -> serve**.

Each stage is independent — ingestion doesn't need the scorer, the scorer doesn't need the API. They communicate through a storage backend (`DbBackend` protocol) — either SQLite (local) or Supabase Postgres (online login).

## Data Flow

All three modes follow the same pipeline: **ingest → dedup → store → score → serve**. They differ in where data lives, who triggers fetches, and how content is served.

### Mode 1: Local

```
config/sources.yml
    │
    ▼
APScheduler (every 30 min)
    │
    ▼
runner.py ─── ingest ──► feeds.py ──► RSS / Atom / RSSHub (incl. XHS)
    │                     twitter.py ──► Twitter GraphQL (Chrome cookies)
    │                     events.py ──► Anthropic / Google event pages
    │                     github_trending.py ──► trendshift.io
    │                     aitmpl_trending.py ──► aitmpl.com (AI tools)
    │                     skillssh_trending.py ──► skills.sh (agent skills)
    │                     (see sources.md for config format and source type details)
    │
    ▼
SqliteBackend (db.py)
    │  id = sha256(url)[:16]
    │  dedup via get_existing_ids()
    │  upsert new items (COALESCE preserves scores)
    │  mark YouTube Shorts duplicates
    │
    ▼
scorer.py ──► Ollama (qwen3:4b)
    │  get_unscored_items(limit=30)
    │  score 0-1, tier, reason per item
    │
    ▼
FastAPI (app.py)
    │  Dashboard: /            ◄── Jinja2 templates
    │  API: /api/items, /api/digest
    │  Admin: /admin (CRUD, password-protected)
    │  Pages: /leaderboard, /events, /trends, /ccc
```

### Mode 2: Online Public

```
config/sources.yml
    │
    ▼
GitHub Action (cron every 2h)
    │  restore cached SQLite artifact
    │
    ▼
cloud_fetch.py ── cloud_fetch_and_score()
    │  runner.py ──► feeds.py (RSS only, no Twitter)
    │
    ▼
SqliteBackend (ephemeral)
    │  id = sha256(url)[:16]
    │  same dedup + upsert as local
    │
    ▼
claude_scorer.py ──► Claude API (optional, needs ANTHROPIC_API_KEY)
    │
    ▼
export.py
    │  items → static/data.json (500 items + dedicated-page items)
    │  config → static/config.json (leaderboard links, event links)
    │
    ▼
git commit + push
    │
    ▼
Vercel (static site)
    │  index.html ──► reads data.json (client-side JS)
    │  leaderboard.html ──► reads config.json
    │  events.html, trends.html, ccc.html ──► reads data.json
    │  admin.html ──► read-only source info
```

### Mode 3: Online Login

```
User signs up / logs in (Supabase Auth)
    │
    ▼
admin.html (browser)
    │  CRUD: user_sources table via PostgREST (RLS: own rows only)
    │  Pre-defined source list on first login (empty content)
    │
    ▼
User clicks "Fetch" or "Fetch All"
    │
    ▼
POST /api/fetch-source (Vercel serverless)
    │  verify JWT → extract user_id
    │  SSRF check on feed URL
    │  fetch RSS/Atom feed
    │  id = sha256(user_id:url)[:16]  ◄── user-scoped ID
    │  dedup via items table (user_id filter)
    │  upsert via upsert_item RPC (service role, scoped by user_id)
    │
    ▼
Supabase Postgres
    │  items (user_id, id, url, title, score, ...)
    │  source_state (source_key, user_id, last_fetched_at)
    │  user_sources (user_id, source_type, name, config, tags)
    │  RLS: each user sees only their own rows
    │  Partial unique indexes: (url) WHERE user_id IS NULL
    │                          (url, user_id) WHERE user_id IS NOT NULL
    │
    ▼
index.html (browser, logged in)
    │  reads items via PostgREST (filtered by auth.uid())
    │  personal feed — only items the user has fetched

─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─

Optional: scheduled batch fetch (GitHub Actions)
    │
    ▼
cloud_fetch.py ── cloud_fetch_all_users()
    │  service role → iterate user_ids from user_sources
    │  per user: SupabaseBackend(user_id=uid)
    │  runner.py ──► feeds.py (user's configured sources)
    │  claude_scorer.py (optional)
```

### Shared Pipeline Components

```
                    ┌─────────────────────────────────────────────┐
                    │            DbBackend Protocol                │
                    │  (storage/backend.py)                        │
                    │                                              │
                    │  get_existing_ids()  ingest_items()          │
                    │  upsert_item()       get_items()             │
                    │  get_unscored_items() count_items()          │
                    │  set_last_fetched()  get_all_tags()          │
                    │  mark_youtube_shorts_duplicates()            │
                    ├──────────────────┬──────────────────────────┤
                    │  SqliteBackend   │  SupabaseBackend          │
                    │  (db.py)         │  (supabase_backend.py)    │
                    │  Mode 1 + 2      │  Mode 3                   │
                    │  WAL, local file │  PostgREST, user_id scope │
                    └──────────────────┴──────────────────────────┘
```

## Data Model

### ContentItem (`models.py`)

The core entity. Every piece of ingested content becomes one `ContentItem`.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Deterministic: `sha256(url)[:16]` (single-tenant) or `sha256(user_id:url)[:16]` (multi-tenant) |
| `url` | `str` | Canonical URL of the content |
| `title` | `str` | Title or first line of the content |
| `summary` | `str` | Short description (from feed or LLM) |
| `content` | `str` | Full text (when available) |
| `source_name` | `str` | Human-readable source label (e.g. "OpenAI Blog") |
| `source_type` | `str` | Display category: `twitter`, `youtube`, `rss`, `arxiv`, `xiaohongshu`, etc. |
| `tags` | `list[str]` | Source-level tags from `sources.yml` |
| `author` | `str` | Content author (when available) |
| `published_at` | `datetime?` | Original publish date |
| `fetched_at` | `datetime` | When the pipeline ingested this item |
| `score` | `float?` | Relevance score 0–1 (set by scorer) |
| `score_reason` | `str` | One-line explanation from LLM |
| `tier` | `str` | `personal` or `work` |
| `is_duplicate_of` | `str?` | Points to the primary item's ID (e.g. YouTube Short → full video) |

### Storage

| Mode | Backend | ID scope | Tables |
|------|---------|----------|--------|
| Local / Online public | `SqliteBackend` | `sha256(url)[:16]` | `items`, `source_state` |
| Online login | `SupabaseBackend` | `sha256(user_id:url)[:16]` | `items`, `source_state`, `user_sources` (RLS by `user_id`) |

Both backends implement the `DbBackend` protocol. Queries filter `WHERE is_duplicate_of IS NULL` to hide soft-duplicates.

### Export (`data.json`)

The static dashboard reads `data.json`, a snapshot exported from the DB:

```json
{
  "exported_at": "2026-03-17T12:00:00Z",
  "period_hours": 168,
  "total": 342,
  "all_tags": ["ai", "infra", ...],
  "items": [ { /* ContentItem fields */ }, ... ]
}
```

Items older than the export window are pruned on each export. The local SQLite DB is also pruned after each fetch cycle. Both windows are configurable — see [Configuration](development.md#configuration). Event and Luma items have a shorter retention: they are removed after the event date plus `AINEWS_EVENT_RETENTION_DAYS` (default 7).

On export, items from the local DB are merged with items already in `data.json` (deduped by ID and URL) so cloud-fetched items survive when the local pipeline overwrites the file.

### Data flow per mode

**Local mode** — no `data.json`, FastAPI reads straight from SQLite:

```
sources.yml → APScheduler (30 min) → runner.py
  ├── feeds.py → RSS/Atom/RSSHub/YouTube
  ├── twitter.py → Twitter GraphQL (Chrome cookies)
  └── ...
       ↓
  SqliteBackend (local .db file)
    dedup: id = sha256(url)[:16], skip existing IDs
       ↓
  scorer.py → Ollama (qwen3:4b)
       ↓
  FastAPI serves dashboard directly from DB
```

**Online public mode** — cloud fetch exports to `data.json`, Vercel serves static:

```
GitHub Actions (cron 2h) → cloud_fetch.py
  └── feeds.py (RSS only, no Twitter)
       ↓
  SqliteBackend (ephemeral, restored from cache artifact)
       ↓
  claude_scorer.py → Claude API
       ↓
  export.py → static/data.json → git push → Vercel
```

**Hybrid (local-push.sh)** — local fetch (incl. Twitter) merged into `data.json`:

```
local-push.sh:
  1. git pull             → get latest cloud data.json
  2. ainews fetch         → local DB (all sources incl. Twitter)
  3. ainews export        → merge local DB + existing data.json → write data.json
  4. git push             → Vercel picks it up
```

## Key Design Decisions

### URL-based dedup
Each item's ID is `sha256(url)[:16]` in single-tenant mode (local/public). In multi-tenant mode (online login), the ID is `sha256(user_id:url)[:16]` so each user gets independent copies of items from shared feeds. Before inserting, `get_existing_ids()` checks the DB in batch. Feeds are re-downloaded every cycle (RSS has no "since" support), but only new items are written. URL uniqueness is enforced per-user via partial indexes.

### Score preservation
The `upsert_item` function uses `COALESCE(excluded.score, items.score)` — if a re-ingested item has `score=None`, the existing score is kept. Scores are only overwritten when the scorer explicitly sets them.

### Sorting: published_at with Luma exception
The dashboard sorts by `published_at` (actual content date) for chronological ordering across sources. Luma events are pushed to the bottom since their `published_at` is the event date (could be weeks in the future). Falls back to `fetched_at` for items without a publish date. Past events (both `events` and `luma` source types) are automatically pruned after the event date (`AINEWS_EVENT_RETENTION_DAYS`, default 7).

### YouTube Shorts dedup
After ingestion, `mark_youtube_shorts_duplicates()` finds Shorts that share a title (case-insensitive) with a full video from the same channel. The Short is marked with `is_duplicate_of` pointing to the full video. The `get_items()` query filters these out via `WHERE is_duplicate_of IS NULL`.

### Sequential scoring
Items are scored one at a time (not in parallel) because Ollama runs a single model instance. Each item takes 15-30s with qwen3:4b. Only 30 unscored items are processed per cycle to avoid blocking.

See [deployment.md](deployment.md) for setup instructions, secrets, and environment variables for each mode.

## Module Map

See [module-map.md](module-map.md) for the full file-by-file listing.

---

*Last updated: 2026-03-22*

