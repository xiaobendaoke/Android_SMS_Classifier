#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="${WSL_RUN_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd -P)}"
OUT="$ROOT/training/reports/experiments/stage0_baseline_20260802"
EXPORT="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/stage0_baseline_20260802_export"
printf 'script_dir=%s\nroot=%s\nout=%s\n' "$SCRIPT_DIR" "$ROOT" "$OUT"
if [[ -d "$OUT" ]]; then
  find "$OUT" -maxdepth 2 -printf '%y %p %s\n' | sort
else
  printf 'report_directory_missing\n'
fi
printf 'export=%s\n' "$EXPORT"
if [[ -d "$EXPORT" ]]; then
  find "$EXPORT" -maxdepth 2 -printf '%y %p %s\n' | sort
  printf '%s\n' '--- command_exit_codes ---'
  cat "$EXPORT/command_exit_codes.txt"
  for log in "$EXPORT"/logs/*.log; do
    printf '%s\n' "--- $(basename "$log") ---"
    tail -n 20 "$log"
  done
else
  printf 'export_directory_missing\n'
fi
