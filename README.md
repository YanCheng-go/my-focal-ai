# AI News Filter

Personal news intelligence system that aggregates AI content from curated sources, scores relevance using a local LLM, and serves a web dashboard + JSON API. Entirely free — no paid APIs.

## Architecture & Data Flow

```
┌─────────────────────────────────────────────────────┐
│                    SOURCES                          │
│                                                     │
│  RSS/Atom (direct)       RSSHub (self-hosted :1200) │
│  ├─ arXiv (3 categories) ├─ Anthropic News          │
│  ├─ OpenAI Blog          └─ Cohere Blog             │
│  ├─ Google DeepMind                                 │
│  ├─ Google Research      Twitter (Chrome cookies)   │
│  ├─ Meta (2 feeds)       └─ GraphQL API + rookiepy  │
│  ├─ Apple ML                                        │
│  ├─ Microsoft Research   YouTube (native RSS)       │
│  ├─ NVIDIA (2 feeds)     ├─ Andrej Karpathy         │
│  ├─ Stability AI         ├─ Nate Herk               │
│  ├─ HuggingFace          └─ TechWorld with Nana     │
│  ├─ Simon Willison                                  │
│  └─ Lilian Weng         Luma Events (via RSSHub)    │
└──────────────┬──────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│  INGESTION (async)                                   │
│  src/ainews/ingest/                                  │
│  ├─ feeds.py    — RSS/Atom via feedparser            │
│  ├─ twitter.py  — Chrome cookies + GraphQL API       │
│  └─ runner.py   — orchestrates all sources           │
│                                                      │
│  Dedup: hash(url) → skip if already in DB            │
│  Tracks last_fetched_at per source                   │
└──────────────┬───────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│  STORAGE — SQLite (WAL mode)                         │
│  data/ainews.db                                      │
│  ├─ items         — all content with scores          │
│  └─ source_state  — last_fetched_at per source       │
└──────────────┬───────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│  SCORING — Ollama (local LLM, default: qwen3:4b)    │
│  src/ainews/scoring/scorer.py                        │
│                                                      │
│  Three principles (config/principles.yml):           │
│  1. Signal over Noise (Shannon)                      │
│  2. Mechanism over Opinion (First Principles)        │
│  3. Builders over Commentators (Skin in the Game)    │
│                                                      │
│  Output per item: score 0-1, tier, reason            │
│  Two tiers: personal (deep technical) / work         │
│  Processes 30 unscored items per cycle               │
└──────────────┬───────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────┐
│  OUTPUT — FastAPI                                    │
│  src/ainews/api/app.py                               │
│  ├─ GET /            — web dashboard (dark theme)    │
│  ├─ GET /api/items   — JSON API (AI-agent friendly)  │
│  ├─ GET /api/digest  — top items from last N hours   │
│  └─ POST /api/fetch  — manual trigger                │
│                                                      │
│  APScheduler: auto fetch+score every 30 min          │
│  Sorted by fetched_at (newest first)                 │
│  Filters: source type, tier, tag, min score          │
└──────────────────────────────────────────────────────┘
```

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
uv run ainews twitter-setup      # verify Chrome cookies for Twitter
uv run ruff check src/           # lint
uv run pytest                    # tests
```

## Documentation

- [docs/architecture.md](docs/architecture.md) — data flow, design decisions, module map
- [docs/sources.md](docs/sources.md) — how to configure and add sources
- [docs/scoring.md](docs/scoring.md) — three principles, tiers, LLM prompt, score interpretation

## Configuration

- `config/sources.yml` — all feed sources (Twitter handles, YouTube channels, RSS URLs, RSSHub routes)
- `config/principles.yml` — scoring principles, tier definitions, dedup settings
- Environment variables prefixed `AINEWS_` override defaults (see `src/ainews/config.py`)

Key env vars:
| Variable | Default | Description |
|---|---|---|
| `AINEWS_OLLAMA_MODEL` | `qwen3:4b` | Ollama model for scoring |
| `AINEWS_FETCH_INTERVAL_MINUTES` | `30` | Auto-fetch interval |
| `AINEWS_DB_PATH` | `data/ainews.db` | SQLite database path |

## How Dedup Works

Each item gets an ID from `sha256(url)[:16]`. On each fetch cycle:
1. Feed is downloaded and parsed into `ContentItem` objects
2. Each item's ID is checked against the DB — existing items are skipped
3. Only new items are inserted; existing scores are never overwritten (upsert uses `COALESCE`)
4. `last_fetched_at` is recorded per source in the `source_state` table
5. YouTube Shorts are auto-marked as duplicates when a full video with the same title exists from the same channel — they stay in the DB but are hidden from the dashboard

## Dashboard

- Dark theme, sorted by `fetched_at` (newest first) — not `published_at`, since events have future dates
- Filters: source type, tier, tag, min score, order by score
- Each item shows: title (linked), score badge (color-coded), source name, source type tag, content tags (up to 3), truncated summary (first 200 chars), score reason
- YouTube Shorts show "YT Short" tag; Luma events show "Event: Mar 24, 2026" with year
- Tags are source-level (defined in `sources.yml`), not per-item

## Twitter (no API key needed)

Twitter ingestion reads cookies directly from Chrome via [rookiepy](https://github.com/nickhealthy/rookiepy). Just stay logged into x.com in Chrome — no API keys or passwords needed. The app calls Twitter's GraphQL API using the browser session.
