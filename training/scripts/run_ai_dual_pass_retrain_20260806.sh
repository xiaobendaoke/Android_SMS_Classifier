#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
REPORT_ROOT="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments"

cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/run_ai_dual_pass_retrain_20260806.py \
  "$ROOT/training/scripts/run_ai_dual_pass_retrain_20260806.py"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/distill_student.py \
  "$ROOT/training/scripts/distill_student.py"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/evaluate.py \
  "$ROOT/training/scripts/evaluate.py"
mkdir -p "$ROOT/training/configs"
cp /mnt/c/dev/Android_SMS_Classifier/training/configs/student.yaml \
  "$ROOT/training/configs/student.yaml"

exec "$ROOT/.venv/bin/python" \
  "$ROOT/training/scripts/run_ai_dual_pass_retrain_20260806.py" \
  --report-root "$REPORT_ROOT"
