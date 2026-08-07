#!/usr/bin/env bash
set -u

ROOT="${WSL_RUN_ROOT:-$HOME/projects/Android_SMS_Classifier}"
RUN="$ROOT/training/data/interim/annotation/ai_dual_pass_20260806_r1"

for status in "$RUN"/status/*.txt; do
  [[ -f "$status" ]] || continue
  if ! grep -q 'exit_code=0' "$status"; then
    slug=$(basename "$status" .txt)
    code=$(grep -oE 'exit_code=[0-9]+' "$status" | head -1)
    attempts=$(grep -oE 'attempts=[0-9]+' "$status" | head -1)
    stderr_bytes=0
    if [[ -f "$RUN/stderr/$slug.txt" ]]; then
      stderr_bytes=$(wc -c < "$RUN/stderr/$slug.txt")
    fi
    echo "FAIL $slug $code $attempts stderr_bytes=$stderr_bytes"
  fi
done | sort | head -40
