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

## Two Modes

### Local (full-featured)
Runs entirely on your machine — SQLite, Ollama, APScheduler, FastAPI dashboard.

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
| Admin | `/admin` | `admin.html` | Source management (local); read-only info (online) |

## Development

### Dev environment (Nix + direnv)

If you use [Nix](https://nixos.org/) and [direnv](https://direnv.net/), the dev environment is fully reproducible — no manual installation of Python, uv, or Docker Compose needed:

```bash
direnv allow   # auto-activates the Nix dev shell (Python 3.12 + uv + docker-compose)
uv sync        # install Python dependencies
```

All system-level tools are declared in `flake.nix`. Add new ones there — never install via `brew`, `apt`, or `npm install -g`.

### Without Nix

Install manually: [Python 3.12+](https://www.python.org/), [uv](https://docs.astral.sh/uv/getting-started/installation/), [Docker](https://docs.docker.com/get-docker/).

```bash
uv sync                          # install deps
uv sync --extra llm --extra dev  # all optional deps (Twitter cookies, dev tools)
```

### Project structure

```
config/           sources.yml (feeds), principles.yml (scoring rules)
src/ainews/
  ingest/         feeds.py, twitter.py, xiaohongshu.py, events.py, github_trending.py
  scoring/        scorer.py (Ollama), claude_scorer.py (Claude API)
  storage/        db.py (SQLite)
  api/            app.py (FastAPI), admin.py
templates/        Jinja2 templates (local server)
static/           Static HTML pages (Vercel deployment)
scripts/          CI and helper scripts
```

### Commands

```bash
uv run ainews serve              # start server (port 8000, auto-reloads)
uv run ainews fetch              # one-time fetch + score (Ollama)
uv run ainews fetch-source "OpenAI"  # fetch a single source
uv run ainews cloud-fetch        # fetch + score with Claude API (for CI)
uv run ainews export             # export data.json + config.json to static/
uv run ruff check src/           # lint (fix before committing)
uv run pytest                    # tests
```

### Workflow

- Branch off `main`, PR when ready, squash merge
- Run `uv run ruff check src/` and `uv run pytest` before committing
- Keep commits small and atomic — one logical change per commit

## Documentation

- [docs/architecture.md](docs/architecture.md) — data flow, design decisions, module map
- [docs/sources.md](docs/sources.md) — how to configure and add sources
- [docs/scoring.md](docs/scoring.md) — three principles, tiers, LLM prompt, score interpretation

## Support

If you find this project useful:

- [Buy Me a Coffee](https://buymeacoffee.com/maverickmiaow)

---

*Last updated: 2026-03-11*
