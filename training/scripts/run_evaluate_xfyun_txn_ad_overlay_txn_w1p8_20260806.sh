#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_txn_ad_overlay_lr_5e4_hard_boundary_both_1p5_txn_w1p8_20260806_r1"

mkdir -p "$ROOT/training/configs"
cp /mnt/c/dev/Android_SMS_Classifier/training/configs/student.yaml \
  "$ROOT/training/configs/student.yaml"

exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/evaluate.py" \
  --test "$ROOT/training/data/processed_transaction_ad_boundary_arbitration_20260806_r1/validation.jsonl" \
  --mode keras \
  --keras "$ROOT/training/artifacts/experiments/$RUN/sms_bytecnn_fp32.keras" \
  --output "/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/$RUN/post_training_keras_metrics.json" \
  --seed 42 \
  --stage "$RUN" \
  --require-acceptance \
  --targets-config "$ROOT/training/configs/student.yaml"
