#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
OUT="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1/connectivity_probe_20260803"
mkdir -p "$OUT"
PROMPT="$OUT/prompt.txt"
STDOUT="$OUT/stdout.txt"
STDERR="$OUT/stderr.txt"
STATUS="$OUT/status.txt"
printf '%s\n' 'Return exactly this JSON object and nothing else: {"status":"ok"}' > "$PROMPT"
set +e
timeout --foreground --signal=TERM 120 bash -ic 'opencode run --model xfyun/xopdeepseekv4flash "$(cat "$1")"' _ "$PROMPT" > "$STDOUT" 2> "$STDERR"
RC=$?
set -e
{
  printf 'model=xfyun/xopdeepseekv4flash\n'
  printf 'exit_code=%s\n' "$RC"
  sha256sum "$PROMPT" "$STDOUT" "$STDERR"
} > "$STATUS"
printf '{"status":"PROBE_COMPLETE","exit_code":%s,"stdout_bytes":%s,"stderr_bytes":%s}\n' "$RC" "$(wc -c < "$STDOUT")" "$(wc -c < "$STDERR")"
exit "$RC"
