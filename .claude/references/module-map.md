# Module Map

- `src/ainews/models.py` — `ContentItem` + `ScoredItem` (Pydantic). Core data structures used throughout the pipeline.
- `src/ainews/cli.py` — CLI entry point: `serve`, `fetch`, `fetch-source`, `list-sources`, `cloud-fetch`, `export`, `backfill-tags`, `explore`.
- `src/ainews/ingest/` — fetches from all sources. `feeds.py` for RSS/Atom (incl. XHS via RSSHub), `twitter.py` for Twitter via Chrome cookies + GraphQL, `events.py` for scraping tech company event pages (Anthropic, Google), `github_trending.py` for trendshift.io scraping, `runner.py` orchestrates and skips existing items.
- `src/ainews/backfill.py` — auto-syncs tags and source_type from `sources.yml` to existing DB items. Runs each fetch cycle (skips via file hash if config unchanged). CLI: `uv run ainews backfill-tags [--dry-run]`.
- `src/ainews/explore.py` — LLM-powered source discovery. Builds prompts from existing sources + principles.yml, calls Ollama or Claude API, deduplicates against existing sources, returns scored suggestions.
- `src/ainews/explore_validate.py` — Post-LLM validation. Checks each suggestion against live services (YouTube RSS feed, Twitter handle, RSS/Atom XML, RSSHub route) to filter hallucinated sources.
- `src/ainews/scoring/scorer.py` — sends unscored items to Ollama with three principles from `config/principles.yml`. Returns score 0-1, tier, reason. `claude_scorer.py` is the cloud alternative using Claude API.
- `src/ainews/storage/backend.py` — `DbBackend` protocol. All storage callers use this interface.
- `src/ainews/storage/db.py` — `SqliteBackend` (WAL) + `get_backend()` factory. `get_existing_ids()` for batch dedup, `upsert_item` preserves existing scores via COALESCE, `ingest_items()` orchestrates dedup+upsert+commit, `source_state` table tracks last fetch per source, `mark_youtube_shorts_duplicates()` hides Shorts when a full video exists.
- `src/ainews/storage/supabase_backend.py` — `SupabaseBackend` (PostgREST). All queries scoped by `user_id`. Item IDs are `sha256(user_id:url)[:16]` for multi-tenant isolation.
- `src/ainews/sources/manager.py` — YAML round-trip read/write for source management (add/edit/delete/toggle). Used by admin UI.
- `src/ainews/sources/supabase_manager.py` — reads `user_sources` table, converts to `sources_config` dict matching `sources.yml` structure.
- `src/ainews/sources/url_constants.py` + `url_resolver.py` — URL parsing: pasted URL → source config fields (platform detection, channel ID extraction). Maps in `rsshub_url_map.json` and `olshansk_feed_map.json` (auto-synced weekly via GitHub Actions).
- `src/ainews/api/app.py` — FastAPI app factory. Detects Vercel via `VERCEL` env var to disable scheduler and static mount. Dashboard sorted by `published_at`, pagination (30/page), search, tag dropdown. Events/luma/CCC/trending items hidden from main feed (dedicated pages).
- `src/ainews/api/admin.py` — Admin UI with password-protected CRUD (local mode only). Auth via session cookies (`AINEWS_ADMIN_PASSWORD`). Protected routes use FastAPI `Depends()`.
- `templates/` — Jinja2 templates (local FastAPI): `_base.html` (shared layout), `dashboard.html`, `admin.html`, `leaderboard.html`, `events.html`, `trends.html`, `ccc.html`, `about.html`.
- `static/` — static site (Vercel): `index.html`, `admin.html` (Supabase Auth + source CRUD for logged-in users), `leaderboard.html`, `events.html`, `trends.html`, `ccc.html`, `about.html`. Shared JS: `nav.js`, `auth-nav.js`, `badges.js`, `shared-config.js`. Shared CSS: `fluid-type.css`. Read from `data.json` + `config.json` (public) or PostgREST (logged-in).
- `api/fetch_source.py` — Vercel serverless function for authenticated per-source fetch. JWT validation, SSRF protection, CORS restriction.
- `api/resolve_url.py` — Vercel serverless function for URL → source field extraction (mirrors `url_resolver.py`).
- `src/ainews/cloud_fetch.py` — cloud pipeline: `cloud_fetch_and_score()` for public mode (GitHub Actions), `cloud_fetch_all_users()` for batch per-user fetches via service role.
- `src/ainews/export.py` — exports `data.json` (scored items) and `config.json` (leaderboard/event links from sources.yml).
- `scripts/check-static-pages.sh` — CI check that warns when a localhost template has no matching static page.
- `e2e/` — Playwright visual regression tests across 6 viewports (mobile, tablet, desktop).
- `tests/perf/` — k6 performance tests with smoke, load, and stress profiles.

For the complete file-by-file module map, see `docs/architecture.md` § Module Map.
