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
runner.py ─── ingest ──► feeds.py ──► RSS / Atom / RSSHub
    │                     twitter.py ──► Twitter GraphQL (Chrome cookies)
    │                     xiaohongshu.py ──► XHS API (Chrome cookies)
    │                     events.py ──► Anthropic / Google event pages
    │                     github_trending.py ──► trendshift.io
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
    │  runner.py ──► feeds.py (RSS only, no Twitter/XHS)
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

## Key Design Decisions

### URL-based dedup
Each item's ID is `sha256(url)[:16]` in single-tenant mode (local/public). In multi-tenant mode (online login), the ID is `sha256(user_id:url)[:16]` so each user gets independent copies of items from shared feeds. Before inserting, `get_existing_ids()` checks the DB in batch. Feeds are re-downloaded every cycle (RSS has no "since" support), but only new items are written. URL uniqueness is enforced per-user via partial indexes.

### Score preservation
The `upsert_item` function uses `COALESCE(excluded.score, items.score)` — if a re-ingested item has `score=None`, the existing score is kept. Scores are only overwritten when the scorer explicitly sets them.

### Sorting: published_at with Luma exception
The dashboard sorts by `published_at` (actual content date) for chronological ordering across sources. Luma events are pushed to the bottom since their `published_at` is the event date (could be weeks in the future). Falls back to `fetched_at` for items without a publish date.

### YouTube Shorts dedup
After ingestion, `mark_youtube_shorts_duplicates()` finds Shorts that share a title (case-insensitive) with a full video from the same channel. The Short is marked with `is_duplicate_of` pointing to the full video. The `get_items()` query filters these out via `WHERE is_duplicate_of IS NULL`.

### Sequential scoring
Items are scored one at a time (not in parallel) because Ollama runs a single model instance. Each item takes 15-30s with qwen3:4b. Only 30 unscored items are processed per cycle to avoid blocking.

## Deployment Modes

### 1. Local Mode
Full pipeline runs on your machine: SQLite + Ollama + APScheduler + FastAPI. Full admin rights.

### 2. Online Public Mode (Vercel + GitHub Actions)
```
GitHub Action (cron every 2h)          Vercel (static site)
┌──────────────────────────┐          ┌──────────────────┐
│ 1. Restore cached SQLite │          │                  │
│ 2. ainews cloud-fetch    │  JSON    │  static/index.html│
│ 3. Score (Claude API,    │ ──────►  │  reads data.json │
│    optional)             │ (commit) │                  │
│ 4. ainews export         │          │                  │
│ 5. git push data.json    │          │                  │
└──────────────────────────┘          └──────────────────┘
```

- Pre-defined sources from `sources.yml`, auto-fetched on schedule
- No persistent database — SQLite is cached as a GitHub Action artifact for dedup
- No backend on Vercel — purely static HTML + JSON
- Data retained for ~1 week (rolling window)
- Scoring is optional (requires `ANTHROPIC_API_KEY` secret)
- Twitter ingestion skipped in CI (no Chrome cookies)

### 3. Online Login Mode (Supabase + Vercel)
```
User (browser)                         Vercel (static + serverless)
┌──────────────────────────┐          ┌──────────────────────────┐
│ 1. Sign up / log in      │          │                          │
│    (Supabase Auth)        │          │  static/admin.html       │
│ 2. Manage source list     │ ──────► │  (CRUD via PostgREST)    │
│ 3. Click "Fetch"          │          │                          │
│                           │          │  POST /api/fetch-source  │
│                           │          │  (Vercel serverless fn)  │
│                           │          │  ↓ verify JWT            │
│                           │          │  ↓ fetch feed            │
│                           │          │  ↓ upsert to Supabase   │
│ 4. View personal feed     │ ◄────── │  static/index.html       │
│                           │          │  (reads via PostgREST)   │
└──────────────────────────┘          └──────────────────────────┘
```

- Each user has isolated data via Row Level Security (`user_id` on all tables)
- Item IDs are user-scoped: `sha256(user_id:url)[:16]` — same feed, independent items per user
- New users get a pre-defined source list but **empty content** (fetch on demand)
- `user_sources` table stores per-user source configuration (replaces `sources.yml`)
- Serverless function (`api/fetch_source.py`) handles authenticated fetches with SSRF protection
- Optional: GitHub Actions batch job (`cloud_fetch_all_users()`) for scheduled per-user fetches

## Secrets & Environment Variables

Three separate systems need credentials to talk to Supabase. Each system runs on a different server and has its own secret storage.

### GitHub Actions (repository secrets)

Set in: GitHub → repo Settings → Secrets and variables → Actions

| Secret | Source | Used by |
|--------|--------|---------|
| `SUPABASE_ACCESS_TOKEN` | Supabase → Account settings → Access Tokens | `migrations.yml` (CLI auth for `db push`) |
| `SUPABASE_PROJECT_REF` | Project URL `https://<ref>.supabase.co` → the `<ref>` part | `migrations.yml` (which project to push to) |
| `AINEWS_SUPABASE_URL` | Supabase → Settings → Data API → Project URL | `fetch.yml`, `export-static.yml` (cloud fetch + export) |
| `AINEWS_SUPABASE_KEY` | Supabase → Settings → API Keys → Publishable key | `fetch.yml`, `export-static.yml` (read access) |

### Vercel (environment variables)

Set in: Vercel → project Settings → Environment Variables (check Production + Preview)

| Env var | Source | Used by |
|---------|--------|---------|
| `AINEWS_SUPABASE_URL` | Supabase → Settings → Data API → Project URL | `api/fetch_source.py` (serverless function) |
| `AINEWS_SUPABASE_KEY` | Supabase → Settings → API Keys → Publishable key | `api/fetch_source.py` (JWT verification) |
| `AINEWS_SUPABASE_SERVICE_KEY` | Supabase → Settings → API Keys → Secret key | `api/fetch_source.py` (write items, bypasses RLS) |

### Browser (public, via config.json)

Exported automatically by `ainews export` — no manual setup needed.

| Key in config.json | Used by |
|--------------------|---------|
| `supabase_url` | `index.html`, `admin.html` (Supabase Auth + PostgREST queries) |
| `supabase_anon_key` | `index.html`, `admin.html` (same as publishable key) |

### Why secrets are duplicated

GitHub Actions and Vercel are **separate servers** that both need to connect to Supabase. They don't share memory or environment — each needs its own copy of the keys, stored in its own secret manager.

## Module Map

```
src/ainews/
├── models.py          ContentItem + ScoredItem (Pydantic)
├── config.py          Settings (env vars), load_sources(), load_principles()
├── cli.py             CLI entry: serve, fetch, cloud-fetch, export
├── export.py          Export scored items to JSON for static site
├── cloud_fetch.py     Cloud pipeline: fetch feeds + optional Claude scoring
├── backfill.py        Re-sync source config (tags, source_type) to existing DB items
├── ingest/
│   ├── feeds.py       RSS/Atom fetching + URL builder for all source types
│   ├── twitter.py     Chrome cookies (rookiepy) + Twitter GraphQL API
│   ├── events.py      Tech company event page scrapers (Anthropic, Google)
│   ├── github_trending.py  Trendshift.io scraper (daily + history)
│   ├── xiaohongshu.py Chrome cookies + XHS API
│   └── runner.py      Orchestrates ingestion, dedup, Shorts marking
├── scoring/
│   ├── scorer.py      Ollama LLM scoring (local)
│   └── claude_scorer.py  Claude API scoring (cloud)
├── storage/
│   ├── backend.py     DbBackend protocol (interface for SQLite + Supabase)
│   ├── db.py          SqliteBackend + get_backend() factory
│   └── supabase_backend.py  SupabaseBackend (PostgREST, user_id scoping)
├── sources/
│   ├── manager.py         YAML round-trip read/write for source management (admin)
│   ├── supabase_manager.py  Read user_sources from Supabase, convert to config
│   ├── url_constants.py   Shared constants for URL parsing (host sets, regex patterns)
│   └── url_resolver.py    Async URL resolver: pasted URL → source config fields
└── api/
    ├── app.py         FastAPI: dashboard, JSON API, scheduler
    └── admin.py       Admin UI with auth (local mode)

config/
├── sources.yml        All feed sources with tags
└── principles.yml     Scoring principles, tiers, proximity model

static/
├── index.html         Static dashboard (reads data.json; or PostgREST for logged-in users)
├── admin.html         Source CRUD + fetch (Supabase Auth); read-only fallback
├── leaderboard.html   AI benchmark links (reads config.json)
├── events.html        Event calendars + scraped events (reads config.json + data.json)
├── trends.html        GitHub trending repos (reads data.json)
├── ccc.html           Claude Code Changelogs (reads data.json)
├── about.html         About page
├── logo.svg           Brand logo
├── logo-text.svg      Logo with text
├── auth-nav.js        Shared Sign in / Logout indicator (Supabase Auth)
├── nav.js             Shared navigation + hamburger menu
├── badges.js          Shared notification badge logic
├── shared-config.js   Shared Supabase config + source type schema
├── fluid-type.css     Fluid typography (responsive font sizes)
├── data.json          Exported items (generated by ainews export)
└── config.json        Leaderboard + event links (generated by ainews export)

api/
├── fetch_source.py    Vercel serverless: JWT-authenticated per-source fetch
└── resolve_url.py     Vercel serverless: URL → source field extraction

supabase/migrations/
├── 20260301000000_initial_schema.sql   Base schema (items, source_state, RPCs)
└── 20260314000000_user_accounts.sql    user_id columns, user_sources, RLS, updated RPCs

templates/
├── _base.html         Shared base template (nav, theme, layout)
├── dashboard.html     Jinja2 dark-theme dashboard (local FastAPI)
├── leaderboard.html   Leaderboard page
├── events.html        Events page with filter tabs
├── trends.html        GitHub trending page with filter tabs
├── ccc.html           Claude Code Changelogs page
├── about.html         About page
└── admin.html         Source management page

.github/workflows/
├── ci.yml             Lint + test + static page check on push/PR
├── fetch.yml          Cron fetch + export + commit (for Vercel)
├── export-static.yml  Re-export config.json when sources.yml changes
├── codeql.yml         CodeQL static analysis (injection, XSS) on PR + weekly
├── migrations.yml     Supabase migration push on merge
├── branch-naming.yml  Enforce branch naming conventions
└── release-drafter.yml  Auto-draft release notes from PR labels

e2e/                   Playwright visual regression tests (6 viewports)
tests/perf/            k6 performance tests (smoke, load, stress profiles)
vercel.json            Vercel config (serves static/ directory)
```

---

*Last updated: 2026-03-15*

