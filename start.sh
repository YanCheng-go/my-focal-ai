#!/usr/bin/env bash
set -euo pipefail

# AI News Filter — one-command launcher
# Usage: ./start.sh          Start all services + app
#        ./start.sh stop     Stop all services

APP_PORT="${AINEWS_PORT:-8000}"
RSSHUB_PORT=1200
OLLAMA_MODEL="${AINEWS_OLLAMA_MODEL:-qwen3:4b}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[ok]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!!]${NC} $1"; }
fail()  { echo -e "${RED}[err]${NC} $1"; }

# --- Stop mode ---
if [[ "${1:-}" == "stop" ]]; then
    echo "Stopping services..."
    if docker compose -f docker/docker-compose.yml ps --quiet 2>/dev/null | grep -q .; then
        docker compose -f docker/docker-compose.yml down
        info "RSSHub stopped"
    fi
    # Stop ainews server if running
    if lsof -ti :"$APP_PORT" &>/dev/null; then
        kill "$(lsof -ti :"$APP_PORT")" 2>/dev/null && info "App stopped (port $APP_PORT)"
    fi
    exit 0
fi

echo ""
echo "  AI News Filter"
echo "  ─────────────────"
echo ""

# --- Check prerequisites ---
missing=0

if ! command -v uv &>/dev/null; then
    fail "uv not found — install from https://docs.astral.sh/uv/"
    missing=1
fi

if ! command -v docker &>/dev/null; then
    warn "Docker not found — RSSHub sources won't work"
fi

if ! command -v ollama &>/dev/null; then
    warn "Ollama not found — scoring will be skipped"
fi

if [[ $missing -eq 1 ]]; then
    exit 1
fi

# --- Install deps ---
echo "Installing dependencies..."
uv sync --quiet
info "Dependencies installed"

# --- Start RSSHub ---
if command -v docker &>/dev/null && [[ -f docker/docker-compose.yml ]]; then
    if ! curl -s "http://localhost:$RSSHUB_PORT" &>/dev/null; then
        echo "Starting RSSHub..."
        docker compose -f docker/docker-compose.yml up -d --quiet-pull 2>/dev/null
        # Wait for RSSHub to be ready
        for i in {1..15}; do
            if curl -s "http://localhost:$RSSHUB_PORT" &>/dev/null; then
                break
            fi
            sleep 1
        done
        if curl -s "http://localhost:$RSSHUB_PORT" &>/dev/null; then
            info "RSSHub running on port $RSSHUB_PORT"
        else
            warn "RSSHub didn't start — some feeds may not work"
        fi
    else
        info "RSSHub already running on port $RSSHUB_PORT"
    fi
fi

# --- Start Ollama ---
if command -v ollama &>/dev/null; then
    if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
        echo "Starting Ollama..."
        ollama serve &>/dev/null &
        sleep 2
    fi
    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        # Pull model if not present
        if ! ollama list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
            echo "Pulling $OLLAMA_MODEL (first time only)..."
            ollama pull "$OLLAMA_MODEL"
        fi
        info "Ollama ready (model: $OLLAMA_MODEL)"
    else
        warn "Ollama didn't start — scoring will be skipped"
    fi
fi

# --- Start app ---
echo ""
info "Starting dashboard at http://localhost:$APP_PORT"
echo "    Press Ctrl+C to stop"
echo ""
uv run ainews serve
