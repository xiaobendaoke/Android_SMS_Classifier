#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_carrier_repayment_teacher_threshold_audit_20260805_r1"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/$RUN"

mkdir -p "$TARGET"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/analyze_teacher_thresholds.py \
  "$ROOT/training/scripts/analyze_teacher_thresholds.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/analyze_teacher_thresholds.py" \
  --model "$ROOT/training/artifacts/experiments/stage2_xfyun_carrier_repayment_teacher_20260805_r1" \
  --validation "$ROOT/training/data/processed_xfyun_carrier_repayment_relabel_20260804_r1/validation.jsonl" \
  --output "$TARGET/threshold_analysis.json"
