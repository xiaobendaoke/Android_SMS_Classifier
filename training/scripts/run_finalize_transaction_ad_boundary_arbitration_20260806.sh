#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SRC="/mnt/c/dev/Android_SMS_Classifier/training/scripts"
cp -f "$SRC/finalize_harass_boundary_arbitration_20260806.py" "$ROOT/training/scripts/finalize_harass_boundary_arbitration_20260806.py"
export PYTHONPATH="$ROOT/training"
exec "$ROOT/.venv/bin/python" \
  "$ROOT/training/scripts/finalize_harass_boundary_arbitration_20260806.py" \
  --run-id "transaction_ad_boundary_arbitration_20260806_r1" \
  --base-data "$ROOT/training/data/processed_harass_fraud_boundary_arbitration_20260806_r1" \
  --selection "zh_transaction_ad_model_boundary_misclassified_stacked"
