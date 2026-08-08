#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
REPORT_ROOT="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/run_xfyun_carrier_repayment_post_annotation_eval.py "$ROOT/training/scripts/run_xfyun_carrier_repayment_post_annotation_eval.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/run_xfyun_carrier_repayment_post_annotation_eval.py" --report-root "$REPORT_ROOT"
