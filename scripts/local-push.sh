#!/usr/bin/env bash
# Fetch Twitter locally and append to cloud data.json, then push to remote.
# Usage: ./scripts/local-push.sh [--hours 168] [--anytime] [--every INTERVAL]
#
# By default only runs during US active hours (7 AM PT – midnight ET).
# Use --anytime to bypass the time check for manual runs.
# Use --every to loop: e.g. --every 2h, --every 30m, --every 90s.
#
# Cloud CI owns everything except Twitter (RSS/YouTube/arXiv/GitHub Trending).
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
SKIP_TIME_CHECK=false
LOOP_SECONDS=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --hours) HOURS="${2:-168}"; shift 2 ;;
        --anytime) SKIP_TIME_CHECK=true; shift ;;
        --every)
            RAW="${2:?--every requires an interval like 2h, 30m, or 90s}"
            NUM="${RAW%[hms]}"
            UNIT="${RAW: -1}"
            case "$UNIT" in
                h) LOOP_SECONDS=$((NUM * 3600)) ;;
                m) LOOP_SECONDS=$((NUM * 60)) ;;
                s) LOOP_SECONDS=$((NUM)) ;;
                *) echo "Bad interval '$RAW' — use e.g. 2h, 30m, 90s"; exit 1 ;;
            esac
            shift 2 ;;
        *)       echo "Unknown flag: $1"; exit 1 ;;
    esac
done

# Only run during US active hours (7 AM PT – midnight ET = 15:00–05:00 UTC).
# Skip this check with --anytime for manual runs.
if [[ "$SKIP_TIME_CHECK" == false ]]; then
    HOUR_UTC=$(date -u '+%H')
    if (( HOUR_UTC >= 5 && HOUR_UTC < 15 )); then
        echo "$(date '+%Y-%m-%d %H:%M:%S') Skipping: outside US active hours (UTC $HOUR_UTC, window 15–05 UTC)"
        exit 0
    fi
fi

LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/local-push.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG_FILE"; }

run_once() {
    log "==> Fetching Twitter sources..."
    # Read Twitter handles from sources.yml and fetch each one
    for handle in $(uv run ainews list-sources 2>/dev/null | grep '^\s*\[twitter\]' | sed 's/.*@//'); do
        log "    Fetching @${handle}..."
        uv run ainews fetch-source "@${handle}" 2>&1 | tee -a "$LOG_FILE" || true
    done

    # Fetch Twitter sources added by Supabase users (only Twitter, not all feeds)
    if [[ -n "${AINEWS_SUPABASE_URL:-}" && -n "${AINEWS_SUPABASE_SERVICE_KEY:-}" ]]; then
        log "==> Fetching Supabase user Twitter sources..."
        uv run ainews fetch-users-twitter 2>&1 | tee -a "$LOG_FILE"
    else
        log "==> Skipping Supabase user Twitter fetch (AINEWS_SUPABASE_URL/SERVICE_KEY not set)"
    fi

    # Ensure remote URL uses YanCheng-go credentials (not YanCheng-0116).
    REMOTE_URL=$(git remote get-url origin)
    if [[ "$REMOTE_URL" == "https://github.com/"* ]]; then
        git remote set-url origin "${REMOTE_URL/https:\/\/github.com/https://YanCheng-go@github.com}"
    fi

    # Defensive: clear any leftover rebase state from a prior interrupted run,
    # otherwise every subsequent git operation aborts with "already a
    # rebase-merge directory".
    git rebase --abort 2>/dev/null || true

    # Ensure we're on main so the push targets the correct branch. Stash the
    # working tree (e.g. uv.lock churn from a different uv version) once, then
    # restore it when we switch back. Single stash only — no nested stashing.
    ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    DID_STASH=false
    if [[ "$ORIGINAL_BRANCH" != "main" ]]; then
        log "==> Switching from $ORIGINAL_BRANCH to main..."
        if ! git diff --quiet HEAD 2>/dev/null || ! git diff --cached --quiet HEAD 2>/dev/null; then
            git stash push -m "local-push-auto" --quiet
            DID_STASH=true
        fi
        git checkout main --quiet
    fi

    # Restore original branch on function exit
    restore_branch() {
        if [[ "$ORIGINAL_BRANCH" != "main" ]]; then
            git checkout "$ORIGINAL_BRANCH" --quiet 2>/dev/null || true
            if [[ "$DID_STASH" == true ]]; then
                git stash pop --quiet 2>/dev/null || log "WARN: stash pop failed, changes remain in stash"
            fi
        fi
    }
    trap restore_branch RETURN

    # main is a pure publish target: data.json/config.json are machine-generated
    # and never hand-edited here, so hard-reset to origin instead of rebasing.
    # This is self-healing — a previously failed push (unpushed local commit)
    # is discarded, since the data is regenerated from the local DB each run —
    # and it eliminates the rebase conflicts / divergence that left main stuck.
    log "==> Resetting main to latest origin/main..."
    git fetch origin main --quiet
    git reset --hard origin/main 2>&1 | tee -a "$LOG_FILE"

    log "==> Appending Twitter items (last ${HOURS}h) to static/data.json..."
    uv run ainews export --hours "$HOURS" --output static/data.json --source-type twitter 2>&1 | tee -a "$LOG_FILE"

    # Check if anything changed
    if git diff --quiet static/data.json static/config.json 2>/dev/null; then
        log "==> No data changes, nothing to push."
        return 0
    fi

    log "==> Committing and pushing updated data..."
    git add static/data.json static/config.json
    git commit --no-verify -m "Update data.json from local fetch [skip ci]"
    git push

    log "==> Done. Vercel will pick up the new data shortly."
}

# Handle Ctrl-C gracefully in loop mode
trap 'log "==> Stopped."; exit 0' INT TERM

if [[ "$LOOP_SECONDS" -gt 0 ]]; then
    log "==> Loop mode: running every ${LOOP_SECONDS}s (Ctrl-C to stop)"
    while true; do
        run_once || log "WARN: run failed, will retry next cycle"
        log "==> Sleeping ${LOOP_SECONDS}s until next run..."
        sleep "$LOOP_SECONDS"
    done
else
    run_once
fi
