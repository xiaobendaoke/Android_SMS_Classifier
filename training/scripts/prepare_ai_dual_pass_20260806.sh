#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$HOME/projects/Android_SMS_Classifier}"
WIN="/mnt/c/dev/Android_SMS_Classifier"
RUN="$ROOT/training/data/interim/annotation/ai_dual_pass_20260806_r1"
EXPECTED="$ROOT/training/data/interim/annotation/ai_dual_pass_20260806_r1"

if [[ "$RUN" != "$EXPECTED" ]]; then
  echo "Unsafe RUN path: $RUN" >&2
  exit 1
fi

rm -rf "$RUN"
mkdir -p \
  "$ROOT/training/data/interim/annotation/label_conflicts_v2" \
  "$ROOT/training/data/interim/annotation/transaction_specialist_v2" \
  "$ROOT/docs"

cp -f "$WIN/training/data/interim/annotation/label_conflicts_v2/conflict_pool.csv" \
  "$ROOT/training/data/interim/annotation/label_conflicts_v2/conflict_pool.csv"
cp -f "$WIN/training/data/interim/annotation/transaction_specialist_v2/specialist_pool_internal.csv" \
  "$ROOT/training/data/interim/annotation/transaction_specialist_v2/specialist_pool_internal.csv"
cp -f "$WIN/docs/labeling-guide.md" "$ROOT/docs/labeling-guide.md"
cp -f "$WIN/training/scripts/prepare_ai_dual_pass_candidate_pack_20260806.py" \
  "$ROOT/training/scripts/prepare_ai_dual_pass_candidate_pack_20260806.py"
cp -f "$WIN/training/scripts/reconcile_ai_dual_pass_20260806.py" \
  "$ROOT/training/scripts/reconcile_ai_dual_pass_20260806.py"
cp -f "$WIN/training/scripts/finalize_ai_dual_pass_20260806.py" \
  "$ROOT/training/scripts/finalize_ai_dual_pass_20260806.py"
cp -f "$WIN/training/scripts/run_ai_dual_pass_20260806.sh" \
  "$ROOT/training/scripts/run_ai_dual_pass_20260806.sh"

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

cd "$ROOT"
"$PY" training/scripts/prepare_ai_dual_pass_candidate_pack_20260806.py \
  --run-id ai_dual_pass_20260806_r1 \
  --batch-size-a 50 \
  --batch-size-b 25
