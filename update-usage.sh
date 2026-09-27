#!/bin/bash
# Keep the host collectors, adding Claude cooldown/error handling locally.
set -u
args=()
claude_enabled=true
selected=()
while (( $# )); do
  case "$1" in
    --except)
      [[ "$2" == claude ]] && claude_enabled=false
      args+=("$1" "$2")
      shift 2 ;;
    --force|--limits-only) args+=("$1"); shift ;;
    *) selected+=("$1"); args+=("$1"); shift ;;
  esac
done
if (( ${#selected[@]} )); then
  found=false
  for id in "${selected[@]}"; do [[ "$id" == claude ]] && found=true; done
  [[ "$found" == false ]] && claude_enabled=false
fi
omarchy-agent-usage-update --except claude "${args[@]}" &
host_pid=$!
status=0
if [[ "$claude_enabled" == true ]]; then
  flags=()
  for arg in "${args[@]}"; do
    case "$arg" in --force|--limits-only) flags+=("$arg");; esac
  done
  python3 "$(dirname -- "$0")/refresh-claude.py" "${flags[@]}" || status=1
fi
wait "$host_pid" || status=1
exit "$status"
