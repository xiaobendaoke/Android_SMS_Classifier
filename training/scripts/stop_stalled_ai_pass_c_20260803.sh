#!/usr/bin/env bash
set -euo pipefail

PIDS=$(pgrep -f '[o]pencode run --model xfyun/xopdeepseekv4flash' || true)
if [[ -z "$PIDS" ]]; then
  printf '%s\n' '{"status":"NO_ACTIVE_PASS_C_PROCESS"}'
  exit 0
fi

for pid in $PIDS; do
  kill -TERM "$pid"
done
printf '{"status":"TERMINATION_REQUESTED","process_count":%s}\n' "$(wc -w <<<"$PIDS")"
