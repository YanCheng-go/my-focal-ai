#!/usr/bin/env bash
# Fetch all sources locally (including Twitter), export, and push to remote.
# Usage: ./scripts/local-push.sh [--hours 168]
#
# This is the hybrid workflow: local fetch (with Chrome cookies for Twitter)
# + cloud serve (Vercel picks up the pushed static/data.json).
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
if [[ "${1:-}" == "--hours" ]]; then
    HOURS="${2:-168}"
fi

LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/local-push.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

log "==> Fetching all sources (including Twitter)..."
uv run ainews fetch 2>&1 | tee -a "$LOG_FILE"

# Fetch Twitter sources added by Supabase users (only Twitter, not all feeds)
if [[ -n "${AINEWS_SUPABASE_URL:-}" && -n "${AINEWS_SUPABASE_SERVICE_KEY:-}" ]]; then
    log "==> Fetching Supabase user Twitter sources..."
    uv run ainews fetch-users-twitter 2>&1 | tee -a "$LOG_FILE"
else
    log "==> Skipping Supabase user Twitter fetch (AINEWS_SUPABASE_URL/SERVICE_KEY not set)"
fi

log "==> Exporting last ${HOURS}h to static/data.json..."
uv run ainews export --hours "$HOURS" --output static/data.json 2>&1 | tee -a "$LOG_FILE"

# Check if anything changed
if git diff --quiet static/data.json static/config.json 2>/dev/null; then
    log "==> No data changes, nothing to push."
    exit 0
fi

log "==> Committing and pushing updated data..."
git add static/data.json static/config.json
git commit -m "Update data.json from local fetch [skip ci]"
git pull --rebase --autostash origin main
git push

log "==> Done. Vercel will pick up the new data shortly."
