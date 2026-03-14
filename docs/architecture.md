# Architecture

## Overview

AI News Filter follows a linear pipeline: **ingest -> dedup -> store -> score -> serve**.

Each stage is independent — ingestion doesn't need the scorer, the scorer doesn't need the API. They communicate through a storage backend (`DbBackend` protocol) — either SQLite (local) or Supabase Postgres (online login).

## Data Flow

```
Sources (RSS, Twitter, YouTube, RSSHub, Luma, GitHub Trending)
    │
    ▼
Ingestion (async, per-source)
    │  fetch feed → parse entries → create ContentItem
    │  check item_exists(hash(url)) → skip if already in DB
    │  upsert only new items
    │  mark YouTube Shorts as duplicates of matching full videos
    │  record last_fetched_at per source
    │
    ▼
SQLite (WAL mode)
    │  items table: all content + scores
    │  source_state table: last_fetched_at per source
    │
    ▼
Scoring (Ollama, sequential)
    │  get_unscored_items(limit=30)
    │  send each to LLM with three principles + tier definitions
    │  parse JSON response → update score, tier, reason in DB
    │  COALESCE prevents re-ingestion from overwriting scores
    │
    ▼
Serving (FastAPI + static)
    │  Dashboard: sorted by published_at (Luma events pushed to bottom)
    │  Dedicated pages: Leaderboard, Events (3 tabs), Trends (2 tabs), CCC
    │  JSON API: /api/items, /api/digest
    │  APScheduler: auto-runs ingest+score every 30 min
    │  Static site: Vercel serves client-side JS pages reading data.json + config.json
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
- Serverless function (`api/fetch-source.py`) handles authenticated fetches with SSRF protection
- Optional: GitHub Actions batch job (`cloud_fetch_all_users()`) for scheduled per-user fetches

## Module Map

```
src/ainews/
├── models.py          ContentItem + ScoredItem (Pydantic)
├── config.py          Settings (env vars), load_sources(), load_principles()
├── cli.py             CLI entry: serve, fetch, cloud-fetch, export
├── export.py          Export scored items to JSON for static site
├── cloud_fetch.py     Cloud pipeline: fetch feeds + optional Claude scoring
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
│   └── supabase_manager.py  Read user_sources from Supabase, convert to config
└── api/
    └── app.py         FastAPI: dashboard, JSON API, scheduler

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
├── auth-nav.js        Shared Sign in / Logout indicator (Supabase Auth)
├── badges.js          Shared notification badge logic
├── data.json          Exported items (generated by ainews export)
└── config.json        Leaderboard + event links (generated by ainews export)

api/
└── fetch-source.py    Vercel serverless: JWT-authenticated per-source fetch

sql/
├── supabase_schema.sql      Base Supabase schema (items, source_state, RPCs)
└── 002_user_accounts.sql    Migration: user_id columns, user_sources, RLS, updated RPCs

templates/
├── dashboard.html     Jinja2 dark-theme dashboard (local FastAPI)
├── leaderboard.html   Leaderboard page
├── events.html        Events page with filter tabs
├── trends.html        GitHub trending page with filter tabs
├── ccc.html           Claude Code Changelogs page
└── admin.html         Source management page

.github/workflows/
├── ci.yml             Lint + test + static page check on push/PR
├── fetch.yml          Cron fetch + export + commit (for Vercel)
└── export-static.yml  Re-export config.json when sources.yml changes

vercel.json            Vercel config (serves static/ directory)
```

---

*Last updated: 2026-03-14*
