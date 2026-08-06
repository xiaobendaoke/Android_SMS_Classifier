#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SRC="/mnt/c/dev/Android_SMS_Classifier/training/scripts"
cp -f "$SRC/run_harass_boundary_arbitration_20260806.py" "$ROOT/training/scripts/run_harass_boundary_arbitration_20260806.py"
cp -f "$SRC/direct_xfyun_call.py" "$ROOT/training/scripts/direct_xfyun_call.py"
mkdir -p "$ROOT/docs"
cp -f "/mnt/c/dev/Android_SMS_Classifier/docs/labeling-guide.md" "$ROOT/docs/labeling-guide.md"
export PYTHONPATH="$ROOT/training"
exec "$ROOT/.venv/bin/python" \
  "$ROOT/training/scripts/run_harass_boundary_arbitration_20260806.py" \
  --run-id "harass_fraud_boundary_arbitration_20260806_r1"
