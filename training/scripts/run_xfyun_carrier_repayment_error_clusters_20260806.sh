#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
REPORT_ROOT="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments"

cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/analyze_xfyun_carrier_repayment_error_clusters_20260806.py \
  "$ROOT/training/scripts/analyze_xfyun_carrier_repayment_error_clusters_20260806.py"

exec "$ROOT/.venv/bin/python" \
  "$ROOT/training/scripts/analyze_xfyun_carrier_repayment_error_clusters_20260806.py" \
  --report-root "$REPORT_ROOT" \
  --model "lr_5e4=$ROOT/training/artifacts/experiments/stage2_xfyun_carrier_repayment_lr_5e4_20260805_r1/sms_bytecnn_fp32.keras" \
  --model "lr_5e4_focal_0p75=$ROOT/training/artifacts/experiments/stage2_xfyun_carrier_repayment_lr_5e4_focal_gamma_0p75_20260806_r1/sms_bytecnn_fp32.keras" \
  --model "dropout_0p10=$ROOT/training/artifacts/experiments/stage2_xfyun_carrier_repayment_dropout_0p10_20260805_r1/sms_bytecnn_fp32.keras" \
  --model "dropout_0p10_focal_0p75=$ROOT/training/artifacts/experiments/stage2_xfyun_carrier_repayment_dropout_0p10_focal_gamma_0p75_20260805_r1/sms_bytecnn_fp32.keras"
