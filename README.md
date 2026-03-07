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

- `config/sources.yml` — all feed sources (Twitter, YouTube, RSS, RSSHub, Luma, arXiv)
- `config/principles.yml` — scoring principles and tier definitions
- Environment variables prefixed `AINEWS_` override defaults (see `src/ainews/config.py`)
- `AINEWS_SCORING=false` — disable Ollama scoring (fetch only)

## Documentation

- [docs/architecture.md](docs/architecture.md) — data flow, design decisions, module map
- [docs/sources.md](docs/sources.md) — how to configure and add sources
- [docs/scoring.md](docs/scoring.md) — three principles, tiers, LLM prompt, score interpretation

---

*Last updated: 2026-03-07*
