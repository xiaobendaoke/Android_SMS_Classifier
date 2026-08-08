#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
REPORT_ROOT="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments"
MODEL="$ROOT/training/artifacts/experiments/stage2_xfyun_carrier_repayment_lr_5e4_20260805_r1/sms_bytecnn_fp32.keras"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/audit_xfyun_carrier_repayment_lr_5e4_logit_bias_20260806.py "$ROOT/training/scripts/audit_xfyun_carrier_repayment_lr_5e4_logit_bias_20260806.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/audit_xfyun_carrier_repayment_lr_5e4_logit_bias_20260806.py" --report-root "$REPORT_ROOT" --model "$MODEL"
