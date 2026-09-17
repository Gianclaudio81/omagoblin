#!/usr/bin/env bash

set -euo pipefail

codex_state_dir="${CODEX_HOME:-$HOME/.codex}/sessions"
[[ -d "$codex_state_dir" ]] || exit 0

latest_session=$(
  find "$codex_state_dir" -type f -name '*.jsonl' -printf '%T@\t%p\n' 2>/dev/null |
    sort -nr |
    sed -n '1p' |
    cut -f 2-
)
[[ -n "$latest_session" ]] || exit 0

jq -r 'select(.type == "turn_context") | .payload.model // empty' "$latest_session" 2>/dev/null |
  tail -n 1
