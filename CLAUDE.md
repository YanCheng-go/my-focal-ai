# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MyFocalAI — personal news intelligence system. Aggregates content from Twitter/X, Xiaohongshu, YouTube, and RSS feeds via RSSHub, then scores relevance using LLM against user-defined principles. Three modes: local (SQLite + Ollama + FastAPI), online public (static HTML + GitHub Actions + Vercel), and online login (Supabase + user auth + per-user feeds).

## Setup

- **Nix + direnv + uv**: `direnv allow` activates the env. `uv sync` installs Python deps.
- **RSSHub**: `docker compose -f docker/docker-compose.yml up -d` — runs on port 1200
- **Ollama**: must be running locally with the configured model (default: `qwen3:4b`)

## Commands

```bash
uv sync                                    # install deps
uv sync --extra llm --extra dev            # install all optional deps
uv run ainews serve                         # start server (port 8000, auto-reloads)
uv run ainews fetch                         # one-time fetch + score (all sources, Ollama)
uv run ainews fetch-source "OpenAI"         # fetch a single source by name (partial match)
uv run ainews list-sources                  # list all configured sources
uv run ainews backfill-tags                 # re-sync tags/type from config to DB
uv run ainews backfill-tags --dry-run       # preview what would change
uv run ainews cloud-fetch                   # fetch feeds + score with Claude API (for CI)
uv run ainews export                        # export data.json + config.json to static/
uv run ruff check src/                     # lint
uv run pytest                              # tests (unit only)
uv run pytest -m integration               # integration tests (needs `supabase start` + env vars)
```

## Workflow: Adding a New Source

When the user adds a new source to `config/sources.yml`, always ask:
> "Want me to run a one-time fetch for this source? (`uv run ainews fetch-source "<name>"`)"

This fetches historical data immediately instead of waiting for the next scheduled cycle.

## Architecture

See `docs/architecture.md` for the full architecture diagram and data flow.

Pipeline: **ingest -> dedup -> store -> score -> serve**.

- `src/ainews/ingest/` — fetches from all sources. `feeds.py` for RSS/Atom, `twitter.py` for Twitter via Chrome cookies + GraphQL, `events.py` for scraping tech company event pages (Anthropic, Google), `github_trending.py` for trendshift.io scraping, `runner.py` orchestrates and skips existing items.
- `src/ainews/backfill.py` — auto-syncs tags and source_type from `sources.yml` to existing DB items. Runs each fetch cycle (skips via file hash if config unchanged). CLI: `uv run ainews backfill-tags [--dry-run]`.
- `src/ainews/scoring/scorer.py` — sends unscored items to Ollama with three principles from `config/principles.yml`. Returns score 0-1, tier, reason. `claude_scorer.py` is the cloud alternative using Claude API.
- `src/ainews/storage/backend.py` — `DbBackend` protocol. All storage callers use this interface.
- `src/ainews/storage/db.py` — `SqliteBackend` (WAL) + `get_backend()` factory. `get_existing_ids()` for batch dedup, `upsert_item` preserves existing scores via COALESCE, `ingest_items()` orchestrates dedup+upsert+commit, `source_state` table tracks last fetch per source, `mark_youtube_shorts_duplicates()` hides Shorts when a full video exists.
- `src/ainews/storage/supabase_backend.py` — `SupabaseBackend` (PostgREST). All queries scoped by `user_id`. Item IDs are `sha256(user_id:url)[:16]` for multi-tenant isolation.
- `src/ainews/sources/supabase_manager.py` — reads `user_sources` table, converts to `sources_config` dict matching `sources.yml` structure.
- `src/ainews/api/app.py` — FastAPI app factory. Detects Vercel via `VERCEL` env var to disable scheduler and static mount. Dashboard sorted by `published_at`, pagination (30/page), search, tag dropdown. Events/luma/CCC/trending items hidden from main feed (dedicated pages).
- `src/ainews/api/admin.py` — Admin UI with password-protected CRUD (local mode only). Auth via session cookies (`AINEWS_ADMIN_PASSWORD`). Protected routes use FastAPI `Depends()`.
- `templates/` — Jinja2 templates (local FastAPI): `dashboard.html`, `admin.html`, `leaderboard.html`, `events.html`, `trends.html`, `ccc.html`.
- `static/` — static site (Vercel): `index.html`, `admin.html` (Supabase Auth + source CRUD for logged-in users), `leaderboard.html`, `events.html`, `trends.html`, `ccc.html`. Read from `data.json` + `config.json` (public) or PostgREST (logged-in).
- `api/fetch_source.py` — Vercel serverless function for authenticated per-source fetch. JWT validation, SSRF protection, CORS restriction.
- `src/ainews/cloud_fetch.py` — cloud pipeline: `cloud_fetch_and_score()` for public mode (GitHub Actions), `cloud_fetch_all_users()` for batch per-user fetches via service role.
- `src/ainews/export.py` — exports `data.json` (scored items) and `config.json` (leaderboard/event links from sources.yml).
- `scripts/check-static-pages.sh` — CI check that warns when a localhost template has no matching static page.

## Config

All settings via env vars prefixed `AINEWS_` (e.g., `AINEWS_OLLAMA_MODEL=qwen3:4b`). `AINEWS_SCORING=false` disables Ollama scoring. `AINEWS_ADMIN_PASSWORD` enables admin login (when set, admin routes require authentication). Supabase vars: `AINEWS_SUPABASE_URL`, `AINEWS_SUPABASE_KEY`, `AINEWS_SUPABASE_SERVICE_KEY`. `AINEWS_CORS_ORIGIN` restricts cross-origin requests on serverless endpoints. See `src/ainews/config.py` for defaults.

## Deployment Modes

| Mode | Database | Auth | Fetch | Served by |
|------|----------|------|-------|-----------|
| Local (`uv run ainews serve`) | SQLite | Optional (`AINEWS_ADMIN_PASSWORD`) | APScheduler + Ollama | FastAPI |
| Online public | data.json (static) | None (read-only) | GitHub Actions + Claude API | Vercel static |
| Online login | Supabase Postgres | Supabase Auth (email/password) | User-triggered (serverless) | Vercel static + serverless |

## Documentation Rules

- When editing any documentation file (`.md`), always update the `*Last updated: YYYY-MM-DD*` line at the bottom with today's date.

## Planned Features (not yet built)

See [open issues](https://github.com/YanCheng-go/my-focal-ai/issues) for the full backlog. Key items:

- #58 Phone screenshot monitoring (watch synced folder, vision LLM extraction)
- #57 Social activity signals (likes/reposts/comments as relevance boost)
- #31 Per-item tags generated by LLM during scoring (currently tags are source-level only)
- #19 Daily digest output (basic `/api/digest` endpoint exists; LLM summary + email/Telegram not yet built)

---

*Last updated: 2026-03-15*

