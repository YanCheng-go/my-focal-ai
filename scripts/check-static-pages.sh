#!/usr/bin/env bash
# Check that every localhost template page has a corresponding static page.
# Run in CI to catch missing static pages when new routes are added.

set -euo pipefail

TEMPLATES_DIR="templates"
STATIC_DIR="static"

# Pages that have both a template and a static version
# Map: template name -> static file name
declare -A PAGE_MAP=(
    ["dashboard.html"]="index.html"
    ["leaderboard.html"]="leaderboard.html"
    ["events.html"]="events.html"
    ["ccc.html"]="ccc.html"
)

# Templates that are server-only (no static equivalent expected)
SKIP=("admin.html")

missing=0

for tmpl in "$TEMPLATES_DIR"/*.html; do
    name=$(basename "$tmpl")

    # Skip server-only templates
    for skip in "${SKIP[@]}"; do
        [[ "$name" == "$skip" ]] && continue 2
    done

    # Check if we have a mapping
    static_name="${PAGE_MAP[$name]:-$name}"
    if [[ ! -f "$STATIC_DIR/$static_name" ]]; then
        echo "MISSING: $STATIC_DIR/$static_name (for template $name)"
        missing=$((missing + 1))
    fi
done

if [[ $missing -gt 0 ]]; then
    echo ""
    echo "$missing static page(s) missing. Create matching static versions in $STATIC_DIR/."
    exit 1
else
    echo "All template pages have matching static versions."
fi
