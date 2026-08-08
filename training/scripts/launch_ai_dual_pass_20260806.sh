#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$HOME/projects/Android_SMS_Classifier}"
LOG="$ROOT/training/reports/ai_dual_pass_20260806_run.log"

mkdir -p "$(dirname "$LOG")"
cd "$ROOT"
nohup bash "$ROOT/training/scripts/run_ai_dual_pass_20260806.sh" >"$LOG" 2>&1 &
echo "PID=$!"
