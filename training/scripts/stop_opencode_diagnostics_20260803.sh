#!/usr/bin/env bash
set -euo pipefail

HELP=$(pgrep -f '[o]pencode --help' || true)
MODELS=$(pgrep -f '[o]pencode models' || true)
for pid in $HELP $MODELS; do
  kill -TERM "$pid" 2>/dev/null || true
done
printf '{"status":"OPENCODE_DIAGNOSTICS_TERMINATION_REQUESTED","help_processes":%s,"models_processes":%s}\n' "$(wc -w <<<"$HELP")" "$(wc -w <<<"$MODELS")"
