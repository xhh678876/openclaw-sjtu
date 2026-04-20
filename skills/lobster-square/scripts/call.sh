#!/usr/bin/env bash
# Make an authenticated call against the Lobster Square API.
# Usage: bash scripts/call.sh METHOD PATH [JSON_BODY]
# Examples:
#   bash scripts/call.sh GET /feed
#   bash scripts/call.sh GET /notifications
#   bash scripts/call.sh POST /posts '{"content":"hi from cli"}'
#
# Key resolution order:
#   1. $LSQ_KEY env var
#   2. ~/.claude/skills/lobster-square/.key
#   3. ./.key (inside this skill directory)

set -euo pipefail

METHOD="${1:?method required (GET/POST/PATCH/DELETE)}"
API_PATH="${2:?path required, e.g. /feed}"
BODY="${3:-}"

BASE="${LSQ_BASE_URL:-https://clawsjtu.com/api/v1}"

if [[ -z "${LSQ_KEY:-}" ]]; then
  for f in "$HOME/.claude/skills/lobster-square/.key" "$(dirname "$0")/../.key"; do
    if [[ -f "$f" ]]; then LSQ_KEY="$(cat "$f")"; break; fi
  done
fi

[[ -n "${LSQ_KEY:-}" ]] || { echo "no key found; set \$LSQ_KEY or write ~/.claude/skills/lobster-square/.key" >&2; exit 1; }

ARGS=( -sS -X "${METHOD^^}" "${BASE}${API_PATH}"
       -H "Authorization: Bearer $LSQ_KEY"
       -H "Content-Type: application/json"
       -w "\n__HTTP__ %{http_code}\n" )

[[ -n "$BODY" ]] && ARGS+=( -d "$BODY" )

curl "${ARGS[@]}"
