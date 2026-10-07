#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
REPORT_ROOT="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments"

cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/train_teacher.py \
  "$ROOT/training/scripts/train_teacher.py"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/run_xfyun_txn_ad_overlay_teacher_20260806.py \
  "$ROOT/training/scripts/run_xfyun_txn_ad_overlay_teacher_20260806.py"
mkdir -p "$ROOT/training/configs"
cp /mnt/c/dev/Android_SMS_Classifier/training/configs/teacher.yaml \
  "$ROOT/training/configs/teacher.yaml"

exec "$ROOT/.venv/bin/python" \
  "$ROOT/training/scripts/run_xfyun_txn_ad_overlay_teacher_20260806.py" \
  --report-root "$REPORT_ROOT"
