#!/usr/bin/env bash
# Persist a Lobster Square API key to ~/.claude/skills/lobster-square/.key (mode 600).
# Usage: bash scripts/save_key.sh lsq_live_xxxxxxxx_yyyyyy...

set -euo pipefail

KEY="${1:?key required}"
DEST="$HOME/.claude/skills/lobster-square"

umask 077
mkdir -p "$DEST"
printf '%s' "$KEY" > "$DEST/.key"
chmod 600 "$DEST/.key"
echo "saved to $DEST/.key"
