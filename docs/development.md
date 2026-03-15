# Development Guide

Getting set up for local development and contributing to the project.

## Dev Environment

### Option A: Nix + direnv (recommended)

The project includes a `flake.nix` that provides a fully reproducible dev shell — Python 3.12, uv, and docker-compose are all managed by Nix. No manual installation needed.

```bash
direnv allow   # auto-activates the Nix dev shell on cd
uv sync        # install Python dependencies
```

**Adding system tools:** All system-level dependencies go in `flake.nix` under `packages`. Never install via `brew`, `apt`, or `npm install -g`.

```nix
# flake.nix — add new tools here
packages = with pkgs; [
  python312
  uv
  docker-compose
  # add new system tools here
];
```

After editing `flake.nix`, run `direnv allow` to pick up the changes. Commit the updated `flake.lock` alongside `flake.nix`.

### Option B: Manual setup

Install these yourself:
- [Python 3.12+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager
- [Docker](https://docs.docker.com/get-docker/) — for RSSHub

```bash
uv sync                          # install core deps
uv sync --extra llm --extra dev  # all optional deps (Twitter cookies, dev tools)
```

## Project Structure

```
src/ainews/              Pipeline code (ingest, scoring, storage, API)
config/                  sources.yml + principles.yml
templates/               Jinja2 templates (local FastAPI)
static/                  Static HTML + JS + CSS (Vercel)
api/                     Vercel serverless functions
e2e/                     Playwright visual regression tests
tests/                   pytest unit + integration tests
tests/perf/              k6 performance tests
scripts/                 CI and helper scripts
docker/                  Docker Compose for RSSHub
supabase/migrations/     Supabase SQL migrations
```

See [architecture.md § Module Map](architecture.md#module-map) for the full file-by-file listing.

## Commands

```bash
# Server
uv run ainews serve                    # start server (port 8000, auto-reloads)

# Fetching
uv run ainews fetch                    # one-time fetch + score (all sources, Ollama)
uv run ainews fetch-source "OpenAI"    # fetch a single source by name
uv run ainews list-sources             # list all configured sources
uv run ainews cloud-fetch              # fetch + score with Claude API (for CI)

# Export
uv run ainews export                   # export data.json + config.json to static/
uv run ainews export --hours 168       # export last 7 days

# Maintenance
uv run ainews backfill-tags            # re-sync tags/type from config to DB
uv run ainews backfill-tags --dry-run  # preview what would change

# Dev
uv run ruff check src/                 # lint (fix before committing)
uv run pytest                          # run tests
uv run pytest -m integration           # integration tests (needs supabase start)

# Visual regression tests (requires server running on :8000)
npx playwright test                    # run all viewport tests
npx playwright test --update-snapshots # update baseline screenshots

# Performance tests (requires server running on :8000 + k6 installed)
k6 run tests/perf/load-test.js                          # smoke (default)
k6 run -e PROFILE=load tests/perf/load-test.js          # load test
k6 run -e PROFILE=stress tests/perf/load-test.js        # stress test
```

## Configuration

All settings are via environment variables prefixed `AINEWS_`. See `src/ainews/config.py` for defaults.

| Variable | Default | Description |
|----------|---------|-------------|
| `AINEWS_OLLAMA_MODEL` | `qwen3:4b` | Ollama model for local scoring |
| `AINEWS_SCORING` | `true` | Set `false` to disable scoring |
| `AINEWS_ADMIN_PASSWORD` | _(empty)_ | When set, admin routes require login |
| `AINEWS_FETCH_INTERVAL_MINUTES` | `120` | Auto-fetch interval |
| `AINEWS_DB_PATH` | `data/news.db` | SQLite database path |
| `AINEWS_HOST` | `0.0.0.0` | Server bind address |
| `AINEWS_PORT` | `8000` | Server port |
| `AINEWS_SUPABASE_URL` | — | Supabase project URL (online login mode) |
| `AINEWS_SUPABASE_KEY` | — | Supabase anon key (online login mode) |
| `AINEWS_SUPABASE_SERVICE_KEY` | — | Supabase service role key (server-side only) |
| `AINEWS_CORS_ORIGIN` | — | Restrict cross-origin requests (serverless) |

## Workflow

1. **Branch** off `main` — use `feat/`, `fix/`, `docs/`, `chore/` prefixes
2. **Lint and test** before committing:
   ```bash
   uv run ruff check src/
   uv run pytest
   ```
3. **Commit** with imperative mood messages ("Add ...", "Fix ...")
4. **PR** to `main` when ready — squash merge after review
5. **Tag releases** with semver (`v1.2.0`)

## Conventions

- **Tests:** Write tests for non-trivial logic. Skip tests for glue code and one-off scripts.
- **Dependencies:** Keep minimal — every dependency is a maintenance burden. System tools go through Nix, Python deps through uv.
- **Simplicity:** Prefer simple solutions over abstractions. Extract patterns only when repeated three times.
- **Static pages:** When adding a new localhost template, create a matching static page in `static/`.

## Adding a New Source

1. Add the source to `config/sources.yml` under the appropriate type
2. Run a one-time fetch to pull historical data:
   ```bash
   uv run ainews fetch-source "<name>"
   ```
3. Verify it appears on the dashboard at http://localhost:8000

See [docs/sources.md](sources.md) for detailed source configuration.

---

*Last updated: 2026-03-15*
