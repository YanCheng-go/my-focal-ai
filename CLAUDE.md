# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Personal news intelligence system. Aggregates content from Twitter/X, Xiaohongshu, YouTube, and RSS feeds via RSSHub, then scores relevance using LLM (Ollama) against user-defined principles. Serves a web dashboard + JSON API.

## Setup

- **Nix + direnv + uv**: `direnv allow` activates the env. `uv sync` installs Python deps.
- **RSSHub**: `docker compose -f docker/docker-compose.yml up -d` — runs on port 1200
- **Ollama**: must be running locally with the configured model (default: `llama3.2`)

## Commands

```bash
uv sync                          # install deps
uv sync --extra llm --extra dev  # install all optional deps
uv run ainews serve               # start server (port 8000, auto-reloads)
uv run ainews fetch               # one-time fetch + score
uv run ruff check src/            # lint
uv run pytest                     # tests
```

## Architecture

Everything flows through a single pipeline: **ingest -> score -> store -> serve**.

- `config/sources.yml` — defines all feed sources (twitter handles, XHS users, youtube channels, RSS URLs). Each source maps to an RSSHub route or direct feed URL.
- `config/principles.yml` — user-defined scoring principles with two tiers (personal/work), boost/penalize rules, and dedup settings.
- `src/ainews/models.py` — `ContentItem` (normalized content from any source) and `ScoredItem` (LLM scoring result). Everything is a ContentItem regardless of source.
- `src/ainews/ingest/feeds.py` — fetches RSS/Atom feeds, normalizes entries to ContentItem. `build_feed_urls()` converts sources.yml config into fetch-ready URLs.
- `src/ainews/scoring/scorer.py` — sends items to Ollama with principles as context, parses structured JSON response into ScoredItem.
- `src/ainews/storage/db.py` — SQLite with WAL mode. `upsert_item` for idempotent writes, `get_items` with filtering.
- `src/ainews/api/app.py` — FastAPI app. APScheduler runs fetch+score on interval. Serves both `/api/*` JSON endpoints and `/` HTML dashboard.

## Config

All settings via env vars prefixed `AINEWS_` (e.g., `AINEWS_OLLAMA_MODEL=llama3.2`). See `src/ainews/config.py` for defaults.

## Planned Features (not yet built)

- Phone screenshot monitoring (watch synced folder, vision LLM extraction)
- Social activity signals (likes/reposts/comments as relevance boost)
- Content deduplication
- Daily digest output
