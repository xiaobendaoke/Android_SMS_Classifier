#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
REPORT_ROOT="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments"

cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/analyze_ai_dual_pass_retrain_20260808.py \
  "$ROOT/training/scripts/analyze_ai_dual_pass_retrain_20260808.py"

export PYTHONPATH="$ROOT/training"
exec "$ROOT/.venv/bin/python" \
  "$ROOT/training/scripts/analyze_ai_dual_pass_retrain_20260808.py" \
  --report-root "$REPORT_ROOT" \
  --model "retrain=$ROOT/training/artifacts/experiments/ai_dual_pass_retrain_20260806_r1/sms_bytecnn_fp32.keras"
