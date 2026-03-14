# AI News Filter

Personal news intelligence system that aggregates AI content from curated sources, scores relevance using LLM, and serves a web dashboard. Runs locally with Ollama (free) or deployed to Vercel with Claude API scoring.

| Feeds | Admin |
|-------|-------|
| ![Feeds](docs/screenshots/dashboard.png) | ![Admin](docs/screenshots/admin.png) |

## Quick Start (Local)

**Prerequisites:** [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager) and [Docker](https://docs.docker.com/get-docker/) (for RSSHub feeds). That's it.

```bash
git clone https://github.com/YanCheng-go/ai-news-filter.git
cd ai-news-filter
./start.sh              # installs deps, starts RSSHub + Ollama, launches dashboard
```

Open http://localhost:8000 — you're done. The script handles everything.

**Options:**
```bash
./start.sh --no-score   # skip Ollama (just fetch + display, no relevance scoring)
./start.sh stop         # stop all services
```

> **Optional:** Install [Ollama](https://ollama.ai) for local LLM scoring. Without it, `start.sh` still works — it just skips scoring.

## Three Modes

### 1. Local (full-featured)
Runs entirely on your machine — SQLite, Ollama, APScheduler, FastAPI dashboard. Full admin access.

#### Twitter / X (local only)

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

### 2. Online Public (Vercel + GitHub Actions)
Static read-only dashboard. GitHub Action fetches pre-defined feeds on a 2h cron, exports to `static/data.json`, and Vercel serves it. Data is kept for approximately one week.

No database, no backend, no Ollama required. Scoring is optional (needs `ANTHROPIC_API_KEY`).

**Setup:**
1. Connect repo to Vercel (output directory: `static/`)
2. Optionally add `ANTHROPIC_API_KEY` as a GitHub Actions secret for scoring
3. Trigger the "Fetch & Export" workflow manually for the first run

### 3. Online Login (Supabase + Vercel)
Authenticated mode where users create accounts, manage their own source list, and fetch feeds on demand. Each user's data is fully isolated via Row Level Security.

New users get a pre-defined source list but **no pre-fetched content** — items appear only after clicking "Fetch" in the admin UI. Sources can be added, edited, disabled, or removed.

**Setup:**
1. Create a [Supabase](https://supabase.com) project
2. Run migrations: `supabase link --project-ref <ref>` then `supabase db push` (or paste `supabase/migrations/*.sql` in the SQL Editor)
3. Set Vercel environment variables: `AINEWS_SUPABASE_URL`, `AINEWS_SUPABASE_KEY`, `AINEWS_SUPABASE_SERVICE_KEY`
4. Optionally set `AINEWS_CORS_ORIGIN` to restrict cross-origin requests

## Configuration

- `config/sources.yml` — all feed sources (Twitter, YouTube, RSS, RSSHub, Luma, arXiv, GitHub Trending)
- `config/principles.yml` — scoring principles and tier definitions
- Environment variables prefixed `AINEWS_` override defaults (see `src/ainews/config.py`)
- `AINEWS_SCORING=false` — disable Ollama scoring (fetch only)

## Pages

| Page | Local | Vercel | Description |
|------|-------|--------|-------------|
| Feeds | `/` | `index.html` | Main feed with filters, search, pagination |
| Leaderboard | `/leaderboard` | `leaderboard.html` | AI benchmark and ranking sites |
| Events | `/events` | `events.html` | Event calendars, Luma, tech events (3 tabs) |
| Trends | `/trends` | `trends.html` | GitHub trending repos — daily + history (2 tabs) |
| CCC | `/ccc` | `ccc.html` | Claude Code Changelogs |
| Admin | `/admin` | `admin.html` | Source management (local); read-only (public); source CRUD + fetch (login) |

## Development

See [docs/development.md](docs/development.md) for the full guide — dev environment setup (Nix + direnv or manual), project structure, commands, conventions, and workflow.

```bash
# Quick dev setup
direnv allow   # if using Nix (recommended)
uv sync        # install Python deps
uv run ruff check src/ && uv run pytest  # lint + test
```

## Documentation

- [docs/development.md](docs/development.md) — dev setup, project structure, commands, conventions
- [docs/architecture.md](docs/architecture.md) — data flow, design decisions, module map
- [docs/sources.md](docs/sources.md) — how to configure and add sources
- [docs/scoring.md](docs/scoring.md) — three principles, tiers, LLM prompt, score interpretation

## Support

If you find this project useful:

- [Buy Me a Coffee](https://buymeacoffee.com/maverickmiaow)

---

*Last updated: 2026-03-14*
