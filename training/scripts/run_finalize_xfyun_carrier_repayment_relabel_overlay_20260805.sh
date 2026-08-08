#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="xfyun_carrier_repayment_relabel_20260804_r1"
SAFE_REPORT_ROOT="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/$RUN"
mkdir -p "$SAFE_REPORT_ROOT"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/finalize_xfyun_carrier_repayment_relabel_overlay.py "$ROOT/training/scripts/finalize_xfyun_carrier_repayment_relabel_overlay.py"
SAFE_REPORT_ROOT="$SAFE_REPORT_ROOT" exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/finalize_xfyun_carrier_repayment_relabel_overlay.py"
