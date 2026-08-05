#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_carrier_repayment_lr_5e4_txn_weight_1p5_20260806_r1"

exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/evaluate.py" \
  --test "$ROOT/training/data/processed_xfyun_carrier_repayment_relabel_20260804_r1/validation.jsonl" \
  --mode keras \
  --keras "$ROOT/training/artifacts/experiments/$RUN/sms_bytecnn_fp32.keras" \
  --output "/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/$RUN/post_training_keras_metrics.json" \
  --seed 42 \
  --stage "$RUN" \
  --require-acceptance \
  --targets-config "$ROOT/training/configs/student.yaml"
