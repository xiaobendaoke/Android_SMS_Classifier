#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$HOME/projects/Android_SMS_Classifier}"
WIN="/mnt/c/dev/Android_SMS_Classifier"
RUN="$ROOT/training/data/interim/annotation/ai_dual_pass_20260806_r1"

cp -f "$WIN/training/scripts/repair_ai_dual_pass_20260806.py" \
  "$ROOT/training/scripts/repair_ai_dual_pass_20260806.py"
cp -f "$WIN/training/scripts/prepare_ai_dual_pass_candidate_pack_20260806.py" \
  "$ROOT/training/scripts/prepare_ai_dual_pass_candidate_pack_20260806.py"
cp -f "$WIN/training/scripts/reconcile_ai_dual_pass_20260806.py" \
  "$ROOT/training/scripts/reconcile_ai_dual_pass_20260806.py"
cp -f "$WIN/docs/labeling-guide.md" "$ROOT/docs/labeling-guide.md"

"$ROOT/.venv/bin/python" "$ROOT/training/scripts/repair_ai_dual_pass_20260806.py"
exec bash "$RUN/run_repair_all.sh"
