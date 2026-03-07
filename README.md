# AI News Filter

Personal news intelligence system that aggregates AI content from curated sources, scores relevance using a local LLM, and serves a web dashboard + JSON API. Entirely free — no paid APIs.

## Setup

Requires: Python 3.12+, Nix + direnv (optional), Docker (for RSSHub)

```bash
# Install dependencies
uv sync

# Start RSSHub (for Anthropic, Cohere, Luma, XHS)
docker compose -f docker/docker-compose.yml up -d

# Start Ollama with scoring model
ollama serve
ollama pull qwen3:4b

# Run the server (dashboard at http://localhost:8000)
uv run ainews serve
```

## Commands

```bash
uv run ainews serve              # start server (port 8000)
uv run ainews fetch              # one-time fetch + score
uv run ainews fetch-source "OpenAI"  # fetch a single source
uv run ainews list-sources       # list all configured sources
uv run ainews twitter-setup      # verify Chrome cookies for Twitter
uv run ruff check src/           # lint
uv run pytest                    # tests
```

## Configuration

- `config/sources.yml` — all feed sources (Twitter, YouTube, RSS, RSSHub, Luma, arXiv)
- `config/principles.yml` — scoring principles and tier definitions
- Environment variables prefixed `AINEWS_` override defaults (see `src/ainews/config.py`)

## Documentation

- [docs/architecture.md](docs/architecture.md) — data flow, design decisions, module map
- [docs/sources.md](docs/sources.md) — how to configure and add sources
- [docs/scoring.md](docs/scoring.md) — three principles, tiers, LLM prompt, score interpretation
