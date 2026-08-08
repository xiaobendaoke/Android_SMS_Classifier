#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"

cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/prepare_ai_dual_pass_expansion_pack_20260808.py \
  "$ROOT/training/scripts/prepare_ai_dual_pass_expansion_pack_20260808.py"

export PYTHONPATH="$ROOT/training"
exec "$ROOT/.venv/bin/python" \
  "$ROOT/training/scripts/prepare_ai_dual_pass_expansion_pack_20260808.py" \
  --run-id ai_dual_pass_expansion_20260808_r1 \
  --target-coverage 0.25 \
  --seed 42
