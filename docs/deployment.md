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

All settings are via environment variables prefixed `AINEWS_`. See `src/ainews/config.py` for defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `AINEWS_SCORING` | `true` | Set `false` to disable scoring |
| `AINEWS_OLLAMA_MODEL` | `qwen3:4b` | Ollama model for local scoring |
| `AINEWS_ADMIN_PASSWORD` | _(empty)_ | When set, admin routes require login |
| `AINEWS_SUPABASE_URL` | — | Supabase project URL |
| `AINEWS_SUPABASE_KEY` | — | Supabase anon key |
| `AINEWS_SUPABASE_SERVICE_KEY` | — | Supabase service role key |
| `AINEWS_CORS_ORIGIN` | — | Restrict cross-origin requests |

See [development.md](development.md) for additional dev-specific settings.

---

*Last updated: 2026-03-15*
