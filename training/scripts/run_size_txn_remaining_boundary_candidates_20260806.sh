#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SRC="/mnt/c/dev/Android_SMS_Classifier/training/scripts"
cp -f "$SRC/size_txn_remaining_boundary_candidates_20260806.py" \
  "$ROOT/training/scripts/size_txn_remaining_boundary_candidates_20260806.py"
export PYTHONPATH="$ROOT/training"
exec "$ROOT/.venv/bin/python" \
  "$ROOT/training/scripts/size_txn_remaining_boundary_candidates_20260806.py"
