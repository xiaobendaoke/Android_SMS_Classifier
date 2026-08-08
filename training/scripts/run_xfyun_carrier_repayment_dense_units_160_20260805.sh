#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
REPORT_ROOT="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/distill_student.py "$ROOT/training/scripts/distill_student.py"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/run_xfyun_carrier_repayment_dense_units_160_20260805.py "$ROOT/training/scripts/run_xfyun_carrier_repayment_dense_units_160_20260805.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/run_xfyun_carrier_repayment_dense_units_160_20260805.py" --report-root "$REPORT_ROOT"
