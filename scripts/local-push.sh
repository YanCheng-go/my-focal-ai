#!/usr/bin/env bash
# Fetch Twitter locally, merge with cloud data.json, and push to remote.
# Usage: ./scripts/local-push.sh [--hours 168] [--all]
#
# By default only fetches Twitter (cloud pipeline handles RSS/YouTube/arXiv).
# Pass --all to fetch all sources locally.
#
# Also fetches Twitter sources added by Supabase users (if configured).

set -euo pipefail
cd "$(dirname "$0")/.."

# When run from launchd, load the Nix/direnv environment
if command -v direnv &>/dev/null; then
    eval "$(direnv export bash 2>/dev/null)" || true
fi

# Load .env if present (for AINEWS_SUPABASE_* vars)
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

HOURS="168"
FETCH_ALL=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --hours) HOURS="${2:-168}"; shift 2 ;;
        --all)   FETCH_ALL=true; shift ;;
        *)       echo "Unknown flag: $1"; exit 1 ;;
    esac
done

LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/local-push.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

if [[ "$FETCH_ALL" == "true" ]]; then
    log "==> Fetching all sources (--all)..."
    uv run ainews fetch 2>&1 | tee -a "$LOG_FILE"
else
    log "==> Fetching Twitter sources only..."
    # Read Twitter handles from sources.yml and fetch each one
    for handle in $(uv run ainews list-sources 2>/dev/null | grep '^\s*\[twitter\]' | sed 's/.*@//'); do
        log "    Fetching @${handle}..."
        uv run ainews fetch-source "@${handle}" 2>&1 | tee -a "$LOG_FILE" || true
    done
fi

# Fetch Twitter sources added by Supabase users (only Twitter, not all feeds)
if [[ -n "${AINEWS_SUPABASE_URL:-}" && -n "${AINEWS_SUPABASE_SERVICE_KEY:-}" ]]; then
    log "==> Fetching Supabase user Twitter sources..."
    uv run ainews fetch-users-twitter 2>&1 | tee -a "$LOG_FILE"
else
    log "==> Skipping Supabase user Twitter fetch (AINEWS_SUPABASE_URL/SERVICE_KEY not set)"
fi

# Pull latest data.json from remote before export so the merge step in
# export.py can preserve cloud-fetched items that aren't in the local DB.
log "==> Pulling latest data.json from remote..."
git stash --quiet 2>/dev/null || true
git pull --rebase origin main 2>&1 | tee -a "$LOG_FILE"
git stash pop --quiet 2>/dev/null || true

log "==> Exporting last ${HOURS}h to static/data.json (with merge)..."
uv run ainews export --hours "$HOURS" --output static/data.json 2>&1 | tee -a "$LOG_FILE"

# Check if anything changed
if git diff --quiet static/data.json static/config.json 2>/dev/null; then
    log "==> No data changes, nothing to push."
    exit 0
fi

log "==> Committing and pushing updated data..."
git add static/data.json static/config.json
git commit -m "Update data.json from local fetch [skip ci]"
git push

log "==> Done. Vercel will pick up the new data shortly."
