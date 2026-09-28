#!/bin/bash
# Keep the host collectors, wrapping Claude (cooldown/errors) and Codex
# (buffered app-server reads) locally.
set -u
# The shell buffers our stderr; keep only its tail so a noisy collector
# cannot grow that buffer without bound (tail never closes the pipe early).
exec 2> >(tail -c 16384 >&2)
args=()
declare -A wrapped=([claude]=true [codex]=true)
selected=()
while (( $# )); do
  case "$1" in
    --except)
      [[ -n "${wrapped[$2]:-}" ]] && wrapped[$2]=false
      args+=("$1" "$2")
      shift 2 ;;
    --force|--limits-only) args+=("$1"); shift ;;
    *) selected+=("$1"); args+=("$1"); shift ;;
  esac
done
if (( ${#selected[@]} )); then
  for agent in "${!wrapped[@]}"; do
    found=false
    for id in "${selected[@]}"; do [[ "$id" == "$agent" ]] && found=true; done
    [[ "$found" == false ]] && wrapped[$agent]=false
  done
fi
flags=()
for arg in "${args[@]}"; do
  case "$arg" in --force|--limits-only) flags+=("$arg");; esac
done
status=0
# With only wrapped agents selected, the host has nothing left to collect.
host_pid=""
if (( ${#selected[@]} == 0 )) || printf '%s\n' "${selected[@]}" | grep -qvx 'claude\|codex'; then
  omarchy-agent-usage-update --except claude --except codex "${args[@]}" &
  host_pid=$!
fi
pids=()
for agent in claude codex; do
  [[ "${wrapped[$agent]}" == true ]] || continue
  python3 "$(dirname -- "$0")/refresh-$agent.py" "${flags[@]}" &
  pids+=($!)
done
for pid in "${pids[@]}"; do wait "$pid" || status=1; done
[[ -n "$host_pid" ]] && { wait "$host_pid" || status=1; }
exit "$status"
