# Architecture

## Overview

AI News Filter follows a linear pipeline: **ingest -> dedup -> store -> score -> serve**.

Each stage is independent — ingestion doesn't need the scorer, the scorer doesn't need the API. They communicate through SQLite.

## Data Flow

```
Sources (RSS, Twitter, YouTube, RSSHub, Luma)
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
Serving (FastAPI)
    │  Dashboard: sorted by fetched_at (not published_at)
    │  JSON API: /api/items, /api/digest
    │  APScheduler: auto-runs ingest+score every 30 min
```

## Key Design Decisions

### URL-based dedup
Each item's ID is `sha256(url)[:16]`. Before inserting, `item_exists()` checks the DB. This means feeds are re-downloaded every cycle (RSS has no "since" support), but only new items are written. The DB also has a `UNIQUE` constraint on `url` as a safety net.

### Score preservation
The `upsert_item` function uses `COALESCE(excluded.score, items.score)` — if a re-ingested item has `score=None`, the existing score is kept. Scores are only overwritten when the scorer explicitly sets them.

### fetched_at vs published_at
The dashboard sorts by `fetched_at` (when the item entered the system), not `published_at`. This is because:
- Luma events have `published_at` set to the event date (could be weeks in the future)
- Some RSS feeds have unreliable or missing publish dates
- `fetched_at` is always set and reflects recency from the user's perspective

### YouTube Shorts dedup
After ingestion, `mark_youtube_shorts_duplicates()` finds Shorts that share a title (case-insensitive) with a full video from the same channel. The Short is marked with `is_duplicate_of` pointing to the full video. The `get_items()` query filters these out via `WHERE is_duplicate_of IS NULL`.

### Sequential scoring
Items are scored one at a time (not in parallel) because Ollama runs a single model instance. Each item takes 15-30s with qwen3:4b. Only 30 unscored items are processed per cycle to avoid blocking.

## Module Map

```
src/ainews/
├── models.py          ContentItem + ScoredItem (Pydantic)
├── config.py          Settings (env vars), load_sources(), load_principles()
├── cli.py             CLI entry: serve, fetch, twitter-setup
├── ingest/
│   ├── feeds.py       RSS/Atom fetching + URL builder for all source types
│   ├── twitter.py     Chrome cookies (rookiepy) + Twitter GraphQL API
│   └── runner.py      Orchestrates ingestion, dedup, Shorts marking
├── scoring/
│   └── scorer.py      Ollama LLM scoring with three-principle prompt
├── storage/
│   └── db.py          SQLite: schema, upsert, queries, source state, dedup
└── api/
    └── app.py         FastAPI: dashboard, JSON API, scheduler

config/
├── sources.yml        All feed sources with tags
└── principles.yml     Scoring principles, tiers, proximity model

templates/
└── dashboard.html     Jinja2 dark-theme dashboard
```
