#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_error_relabel_pipeline_eval_20260804_r1"
REPORT="$ROOT/training/reports/experiments/$RUN"
mkdir -p "$REPORT"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/evaluate.py" --mode pipeline --keras "$ROOT/training/artifacts/experiments/stage2_xfyun_overlay_txn_weight_1p4_20260803_r1/sms_bytecnn_fp32.keras" --test "$ROOT/training/data/processed_xfyun_error_relabel_20260803_r1/validation.jsonl" --stage "$RUN" --output "$REPORT/evaluation.json" --seed 42
