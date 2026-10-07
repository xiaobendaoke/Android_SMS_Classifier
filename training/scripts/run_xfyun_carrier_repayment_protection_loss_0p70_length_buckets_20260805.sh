#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_carrier_repayment_protection_loss_0p70_20260805_r1"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/$RUN"

mkdir -p "$TARGET"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/analyze_xfyun_overlay_length_buckets.py \
  "$ROOT/training/scripts/analyze_xfyun_overlay_length_buckets.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/analyze_xfyun_overlay_length_buckets.py" \
  --model "$ROOT/training/artifacts/experiments/$RUN/sms_bytecnn_fp32.keras" \
  --validation "$ROOT/training/data/processed_xfyun_carrier_repayment_relabel_20260804_r1/validation.jsonl" \
  --output "$TARGET/analysis.json"
