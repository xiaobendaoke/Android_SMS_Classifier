#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
HOST_ROOT="/mnt/c/dev/Android_SMS_Classifier"
SCRIPT="run_xfyun_carrier_repayment_conv_filters_128_20260805.py"

cp "$HOST_ROOT/training/scripts/$SCRIPT" "$ROOT/training/scripts/$SCRIPT"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/$SCRIPT" \
  --report-root "$HOST_ROOT/training/reports/experiments"
