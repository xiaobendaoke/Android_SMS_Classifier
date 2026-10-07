#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
OUT="$ROOT/training/reports/experiments/stage0_baseline_20260802_r2"
printf 'root=%s\nout=%s\n' "$ROOT" "$OUT"
find "$OUT" -maxdepth 2 -type f -printf '%p %s\n' | sort
printf '%s\n' '--- command_exit_codes ---'
cat "$OUT/command_exit_codes.txt"
for file in "$OUT/current_validation_pipeline.json" "$OUT/dataset_leakage_v2.json"; do
  if [[ -f "$file" ]]; then
    printf '%s\n' "--- $(basename "$file") ---"
    cat "$file"
  fi
done
for log in "$OUT"/logs/*.log; do
  printf '%s\n' "--- $(basename "$log") ---"
  tail -n 30 "$log"
done
