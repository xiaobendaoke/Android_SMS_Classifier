#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_carrier_repayment_weight_1p5_pipeline_eval_20260805_r1"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/$RUN"
mkdir -p "$TARGET"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/evaluate.py" --test "$ROOT/training/data/processed_xfyun_carrier_repayment_relabel_20260804_r1/validation.jsonl" --mode pipeline --keras "$ROOT/training/artifacts/experiments/stage2_xfyun_carrier_repayment_weight_1p5_post_annotation_20260805_r1/sms_bytecnn_fp32.keras" --rules-dir "$ROOT/training/rules/rules" --output "$TARGET/pipeline_metrics.json" --seed 42 --stage "$RUN" --error-samples 0 --require-acceptance --targets-config "$ROOT/training/configs/student.yaml"
