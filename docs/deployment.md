# Deployment Modes

Three ways to run the system — pick whichever fits your setup.

## 1. Local (full-featured)

Runs entirely on your machine — SQLite, Ollama, APScheduler, FastAPI dashboard. Full admin access.

```bash
./start.sh              # installs deps, starts RSSHub + Ollama, launches dashboard
./start.sh --no-score   # skip Ollama (just fetch + display, no relevance scoring)
./start.sh stop         # stop all services
```

### Twitter / X (local only)

Twitter sources are only available in local mode. The fetcher reads your browser's session cookies directly — no API key required — but this approach is against X's Terms of Service, so it cannot be used in the cloud pipeline.

**Prerequisites:**
1. **Log in to X in Chrome** on the same machine. The fetcher reads `auth_token` and `ct0` cookies from your Chrome profile automatically via [`rookiepy`](https://github.com/thewh1teagle/rookiepy).
2. **Install the `llm` extras** (includes `rookiepy`):
   ```bash
   uv sync --extra llm
   ```
3. **Verify the cookie setup:**
   ```bash
   uv run ainews twitter-setup
   ```
4. **Add Twitter sources** to `config/sources.yml` with `type: twitter` and `handle: username`.

> **Why not in the cloud?** The method relies on scraping private GraphQL endpoints using your personal session cookies, which violates [X's Terms of Service](https://x.com/en/tos). Running it in a public CI pipeline would also expose your personal session. Use RSS-based alternatives (e.g. [nitter](https://github.com/zedeus/nitter) via RSSHub) for the cloud pipeline if you need Twitter content.

## 2. Online Public (Vercel + GitHub Actions)

Static read-only dashboard. GitHub Action fetches pre-defined feeds on a 2h cron, exports to `static/data.json`, and Vercel serves it. Data is kept for approximately one week.

No database, no backend, no Ollama required. Scoring is optional (needs `ANTHROPIC_API_KEY`).

**Setup:**
1. Connect repo to Vercel (output directory: `static/`)
2. Optionally add `ANTHROPIC_API_KEY` as a GitHub Actions secret for scoring
3. Trigger the "Fetch & Export" workflow manually for the first run

### Hybrid: Local Fetch + Cloud Serve

Twitter and relevance scoring require local resources (Chrome cookies and Ollama respectively). To get Twitter content and scored items in the online public dashboard, run the fetch locally and push to GitHub:

```bash
./scripts/local-push.sh              # fetch all sources (including Twitter), export, commit + push
./scripts/local-push.sh --hours 48   # export only the last 48 hours
```

The script:
1. Runs `ainews fetch` locally (Twitter works via Chrome cookies, scoring via Ollama)
2. Runs `ainews fetch-users` if Supabase credentials are set (fetches Twitter sources added by online users)
3. Exports to `static/data.json` and pushes to GitHub
4. Vercel auto-deploys the updated data

**Automate with launchd** (macOS):
```bash
# Copy the template and replace /path/to/ai-news-filter with your actual project path
cp scripts/com.ainews.local-push.plist.example ~/Library/LaunchAgents/com.ainews.local-push.plist
# Edit the plist to set your paths, then load it
launchctl load ~/Library/LaunchAgents/com.ainews.local-push.plist
```
This runs the script every 2 hours. Requires granting Full Disk Access to `/bin/bash` in System Settings > Privacy & Security (needed for Chrome cookie access in background).

**Required `.env` for Supabase user fetch:**
```bash
AINEWS_SUPABASE_URL=https://<ref>.supabase.co
AINEWS_SUPABASE_SERVICE_KEY=<service-role-key>   # Settings > API > service_role (secret)
```

Logs are written to `logs/local-push.log` in the project directory.

## 3. Online Login (Supabase + Vercel)

Authenticated mode where users create accounts, manage their own source list, and fetch feeds on demand. Each user's data is fully isolated via Row Level Security.

New users get a pre-defined source list but **no pre-fetched content** — items appear only after clicking "Fetch" in the admin UI. Sources can be added, edited, disabled, or removed.

**Setup:**
1. Create a [Supabase](https://supabase.com) project
2. Run migrations: `supabase link --project-ref <ref>` then `supabase db push` (or paste `supabase/migrations/*.sql` in the SQL Editor)
3. Set Vercel environment variables: `AINEWS_SUPABASE_URL`, `AINEWS_SUPABASE_KEY`, `AINEWS_SUPABASE_SERVICE_KEY`
4. Optionally set `AINEWS_CORS_ORIGIN` to restrict cross-origin requests

## Pages

| Page | Local | Vercel | Description |
|------|-------|--------|-------------|
| Feeds | `/` | `index.html` | Main feed with filters, search, pagination |
| Leaderboard | `/leaderboard` | `leaderboard.html` | AI benchmark and ranking sites |
| Events | `/events` | `events.html` | Event calendars, Luma, tech events (3 tabs) |
| Trends | `/trends` | `trends.html` | GitHub trending repos — daily + history (2 tabs) |
| CCC | `/ccc` | `ccc.html` | Claude Code Changelogs |
| About | `/about` | `about.html` | About page |
| Admin | `/admin` | `admin.html` | Source management (local); read-only (public); source CRUD + fetch (login) |

## Configuration

All settings are via environment variables prefixed `AINEWS_`. See [development.md § Configuration](development.md#configuration) for the full variable table with defaults.

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

---

*Last updated: 2026-03-17*
