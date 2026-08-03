#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_overlay_pipeline_20260803_r1"
OUT="$ROOT/training/reports/experiments/$RUN"
mkdir -p "$OUT"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/evaluate.py" \
  --mode pipeline \
  --keras "$ROOT/training/artifacts/experiments/stage2_xfyun_overlay_txn_weight_1p4_20260803_r1/sms_bytecnn_fp32.keras" \
  --test "$ROOT/training/data/processed_xfyun_ai_annotation_20260802_r1/validation.jsonl" \
  --rules-dir "$ROOT/training/rules/rules" \
  --output "$OUT/evaluate.json" \
  --stage "$RUN" \
  --seed 42
