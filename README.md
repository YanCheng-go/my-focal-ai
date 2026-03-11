# AI News Filter

Personal news intelligence system that aggregates AI content from curated sources, scores relevance using LLM, and serves a web dashboard. Runs locally with Ollama (free) or deployed to Vercel with Claude API scoring.

## Two Modes

### Local (full-featured)
Runs entirely on your machine — SQLite, Ollama, APScheduler, FastAPI dashboard.

```bash
# One-command start (installs deps, starts RSSHub + Ollama, launches dashboard)
./start.sh

# Or without scoring (no Ollama needed — just fetches and displays)
./start.sh --no-score

# Stop all services
./start.sh stop
```

Or manually:
```bash
uv sync
docker compose -f docker/docker-compose.yml up -d
ollama serve && ollama pull qwen3:4b
uv run ainews serve
```

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

### Cloud (Vercel + GitHub Actions)
Static dashboard deployed to Vercel. GitHub Action fetches feeds on a 2h cron, exports to `static/data.json`, and Vercel serves it.

No database, no backend, no Ollama required. Scoring is optional (needs `ANTHROPIC_API_KEY`).

**Setup:**
1. Connect repo to Vercel (output directory: `static/`)
2. Optionally add `ANTHROPIC_API_KEY` as a GitHub Actions secret for scoring
3. Trigger the "Fetch & Export" workflow manually for the first run

## Commands

```bash
# Local
uv run ainews serve              # start server (port 8000)
uv run ainews fetch              # one-time fetch + score (Ollama)
uv run ainews fetch-source "OpenAI"  # fetch a single source
uv run ainews list-sources       # list all configured sources
uv run ainews twitter-setup      # verify Chrome cookies for Twitter

# Cloud / Export
uv run ainews cloud-fetch        # fetch feeds + score with Claude API (no Twitter/Ollama)
uv run ainews export             # export scored items to static/data.json
uv run ainews export --hours 168 # export last 7 days

# Dev
uv run ruff check src/           # lint
uv run pytest                    # tests
```

## Configuration

- `config/sources.yml` — all feed sources (Twitter, YouTube, RSS, RSSHub, Luma, arXiv, GitHub Trending)
- `config/principles.yml` — scoring principles and tier definitions
- Environment variables prefixed `AINEWS_` override defaults (see `src/ainews/config.py`)
- `AINEWS_SCORING=false` — disable Ollama scoring (fetch only)

## Pages

| Page | Local | Vercel | Description |
|------|-------|--------|-------------|
| Dashboard | `/` | `index.html` | Main feed with filters, search, pagination |
| Leaderboard | `/leaderboard` | `leaderboard.html` | AI benchmark and ranking sites |
| Events | `/events` | `events.html` | Event calendars, Luma, tech events (3 tabs) |
| Trends | `/trends` | `trends.html` | GitHub trending repos — daily + history (2 tabs) |
| CCC | `/ccc` | `ccc.html` | Claude Code Changelogs |
| Admin | `/admin` | — | Source management (local only) |

## Documentation

- [docs/architecture.md](docs/architecture.md) — data flow, design decisions, module map
- [docs/sources.md](docs/sources.md) — how to configure and add sources
- [docs/scoring.md](docs/scoring.md) — three principles, tiers, LLM prompt, score interpretation

---

*Last updated: 2026-03-11*
