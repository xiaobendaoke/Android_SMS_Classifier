#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
REPORT_ROOT="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments"
MODEL_075="$ROOT/training/artifacts/experiments/stage2_xfyun_carrier_repayment_dropout_0p10_focal_gamma_0p75_20260805_r1/sms_bytecnn_fp32.keras"
MODEL_100="$ROOT/training/artifacts/experiments/stage2_xfyun_carrier_repayment_dropout_0p10_focal_gamma_1p0_20260805_r1/sms_bytecnn_fp32.keras"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/audit_xfyun_carrier_repayment_logit_bias_20260805.py "$ROOT/training/scripts/audit_xfyun_carrier_repayment_logit_bias_20260805.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/audit_xfyun_carrier_repayment_logit_bias_20260805.py" --report-root "$REPORT_ROOT" --model "$MODEL_075" --model "$MODEL_100"
