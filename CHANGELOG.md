# Changelog

## v0.4.0 — 2026-03-15

### Features

- **Online login mode** — Full Supabase integration with user auth (email/password), per-user feeds, CRUD source management via admin UI, and serverless per-source fetch via Vercel (#92)
- **UI redesign** — New nav bar, onboarding welcome modal, Quick Add URL resolver with platform auto-detection, logo (#127)
- **New-item indicators** — Blue highlight background + "New" pill on items fetched since last visit, per-category badge counts on filter buttons. Cookie-based for local mode, localStorage for static site (#132)
- **Default source seeding** — New users get pre-configured sources on first login (#120)
- **Shared static assets** — Extracted nav, auth-nav, badges, config, and source type schema into reusable JS modules across all static pages

### Fixes

- **Security** — XSS in source_type filter, PostgREST filter injection in search, SSRF DNS rebinding in serverless fetch (#111)
- **Multi-tenant isolation** — User-scoped item IDs (`sha256(user_id:url)`), URL uniqueness per user, RLS policies, duplicate/hidden item leaks
- **Serverless function** — Replace supabase-py with direct httpx calls to fix import shadowing and reduce bundle size (#121)
- **Scoring** — Make `ScoredItem.tier` optional (default "personal") to prevent ValidationError when LLM omits it
- **SQL/badges** — Fix SQL precedence ambiguity, badge timestamp regression, CCC hardcode

### Infrastructure

- **CodeQL** security scanning workflow + comprehensive SECURITY.md audit (#133)
- **67 new unit tests** covering DB, models, backfill, URL resolver, Supabase backend, GitHub trending, scorer (#128)
- **pytest-cov** for automatic coverage reporting (#130)
- Supabase migrations workflow, branch naming CI improvements
- Bump pyjwt 2.11.0 → 2.12.0 (#131)

### Docs

- Architecture diagrams for all three deployment modes (local, online public, online login)
- New deployment guide, development guide, secrets/env vars documentation
- Simplified README — moved deployment details to docs/ (#122, #123)

## v0.3.1 — 2026-03-11

### Features

- **`AINEWS_SHOW_SCORES` feature flag** — Top Only and By Score filters on the dashboard are now hidden by default; set `AINEWS_SHOW_SCORES=true` to re-enable them
- **Buy Me a Coffee** — Support link (coffee emoji) added to the nav bar across all pages

### Fixes

- **Missing publish date** — Items without a `published_at` now show `fetched_at` with a "(fetched)" label instead of showing no date at all. Applied across dashboard, events, trends, and CCC pages (both local templates and static site)

### Docs

- Add dashboard and admin screenshots to README
- Document Twitter/X prerequisites and why it's excluded from the cloud pipeline

## v0.3.0 — 2026-03-09

### Features

- **UI redesign** — Tailwind CSS replaces hand-written inline styles across all templates and static pages. New shared `_base.html` template eliminates ~300 lines of duplicated HTML/CSS.
- **Dark/light theme toggle** — Three-way toggle (light, system, dark) with localStorage persistence across all pages
- **Notification badges** — Red badge counts on Dashboard, Trends, and CCC nav links show new items since last visit, powered by new `/api/badge-counts` endpoint
- **About page** — New About page with project overview and tech stack, plus GitHub repo link in nav on all pages

### Fixes

- **Admin page crash** — Fix crash when `github_trending` config is a dict instead of a list
- **Config normalization** — Normalize `github_trending` config to standard list format
- **CCC badge accuracy** — Use exact `source_name` filter instead of fuzzy search for badge counts

### Infrastructure

- Bump `actions/cache` from v4 to v5
- Add `source_name` filter to `_build_where` / `count_items` in storage layer

## v0.2.0 — 2026-03-09

### Features

- **GitHub Trending page** — trendshift.io scraper fetches top 25 trending repos daily, with two tabs: Daily Trending and Trending History (all-time most-featured repos)
- **Static pages for Vercel** — Leaderboard, Events, CCC, and Trends pages exported as client-side JS for the static site
- **CI: auto-export config** — new workflow re-exports `config.json` when `sources.yml` changes
- **CI: static page check** — warns when a localhost template has no matching static page

### Fixes

- **Export includes dedicated-page items** — trending repos are now guaranteed in `data.json` even when the 500-item limit would otherwise exclude them

### Infrastructure

- Updated CLAUDE.md with static pages architecture and export documentation

## v0.1.0 — 2026-03-09

First release of MyFocalAI — a personal news intelligence system.

### Features

- **Multi-source ingestion** — Twitter/X, YouTube, RSS/Atom, arXiv, Xiaohongshu, Luma events
- **Event scrapers** — Anthropic and Google developer events (HTML scraping)
- **LLM scoring** — Ollama (local) and Claude API (cloud) score items against user-defined principles
- **Web dashboard** — dark theme, filters by source type/tag/score/tier, search, pagination
- **Admin page** — manage sources (add/edit/delete/toggle/fetch) via web UI
- **Leaderboard page** — links to AI model benchmark sites
- **Events page** — event calendar links + scraped events with filter tabs (Calendars, Luma, Tech Events)
- **CCC page** — Claude Code Changelogs (release notes from GitHub Atom feed)
- **Static site export** — JSON export for Vercel-hosted dashboard
- **Config backfill** — auto-sync tags and source_type from `sources.yml` to existing DB items
- **Deduplication** — batch dedup on ingest, YouTube Shorts detection
- **Concurrent Claude scoring** — parallel API calls for cloud scoring

### Infrastructure

- GitHub Actions CI (ruff lint, pytest, scheduled fetch every 2h)
- Vercel static site deployment
- Dependabot for GitHub Actions dependencies
- GitHub config (issue templates, PR template, security policy, editorconfig)
- Nix + direnv + uv for reproducible dev environment
