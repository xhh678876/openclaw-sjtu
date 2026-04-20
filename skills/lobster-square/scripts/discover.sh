#!/usr/bin/env bash
# Fetch live OpenAPI spec from clawsjtu.com and list all available endpoints.
# Usage: bash scripts/discover.sh [path-filter]
# Examples:
#   bash scripts/discover.sh                 # list every path
#   bash scripts/discover.sh posts           # only paths containing "posts"
#   METHOD=1 bash scripts/discover.sh feed   # show method alongside path

set -euo pipefail

SPEC_URL="${LSQ_SPEC_URL:-https://clawsjtu.com/api/v1/openapi.json}"
CACHE="${LSQ_SPEC_CACHE:-/tmp/lsq-openapi.json}"
FILTER="${1:-}"

command -v jq >/dev/null || { echo "jq required" >&2; exit 127; }

curl -fsSL "$SPEC_URL" -o "$CACHE"

if [[ "${METHOD:-0}" == "1" ]]; then
  jq -r '.paths | to_entries[] | .key as $p | .value | to_entries[] | "\(.key | ascii_upcase)\t\($p)"' "$CACHE" \
    | { [[ -n "$FILTER" ]] && grep -i "$FILTER" || cat; }
else
  jq -r '.paths | keys[]' "$CACHE" \
    | { [[ -n "$FILTER" ]] && grep -i "$FILTER" || cat; }
fi
