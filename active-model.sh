#!/usr/bin/env bash

set -euo pipefail

codex_state_dir="${CODEX_HOME:-$HOME/.codex}/sessions"
[[ -d "$codex_state_dir" ]] || exit 0

# find -type f neither follows links nor lists FIFOs; timeout covers a file
# swapped after listing, and the output cap bounds what the shell buffers.
latest_session=$(
  timeout 5 find "$codex_state_dir" -type f -name '*.jsonl' -size -256M -printf '%T@\t%p\n' 2>/dev/null |
    sort -nr |
    sed -n '1p' |
    cut -f 2-
)
[[ -n "$latest_session" ]] || exit 0

timeout 5 jq -r 'select(.type == "turn_context") | .payload.model // empty' < "$latest_session" 2>/dev/null |
  tail -n 1 |
  head -c 128
