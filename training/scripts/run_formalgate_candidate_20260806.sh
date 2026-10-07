#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SRC="/mnt/c/dev/Android_SMS_Classifier/training"
RUN="stage2_xfyun_txn_ad_overlay_lr_5e4_hard_boundary_both_1p5_txn_w1p8_formalgate_20260806_r1"
REPORT_ROOT="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/$RUN"
ARTIFACT="$ROOT/training/artifacts/experiments/$RUN"
REP="$ROOT/training/data/interim/annotation/formalgate_candidate_20260806_r1/representative.jsonl"

mkdir -p "$REPORT_ROOT" "$ARTIFACT" "$(dirname "$REP")"

for f in prune_channels.py quantize_int8.py verify_tflite.py export_android_assets.py generate_representative_manifest.py; do
  cp -f "$SRC/scripts/$f" "$ROOT/training/scripts/$f"
done
mkdir -p "$ROOT/training/configs"
cp -f "$SRC/configs/student_candidate_txn_w1p8_20260806.yaml" "$ROOT/training/configs/student_candidate_txn_w1p8_20260806.yaml"
cp -f "$SRC/configs/pruning_candidate_txn_w1p8_20260806.yaml" "$ROOT/training/configs/pruning_candidate_txn_w1p8_20260806.yaml"
cp -f "$SRC/configs/quantization_candidate_txn_w1p8_20260806.yaml" "$ROOT/training/configs/quantization_candidate_txn_w1p8_20260806.yaml"

export PYTHONPATH="$ROOT/training"

"$ROOT/.venv/bin/python" "$ROOT/training/scripts/generate_representative_manifest.py" \
  --config "$ROOT/training/configs/quantization_candidate_txn_w1p8_20260806.yaml" \
  --train "$ROOT/training/data/processed_transaction_ad_boundary_arbitration_20260806_r1/train.jsonl" \
  --output "$REP" \
  --summary "$REPORT_ROOT/representative_summary.json"

"$ROOT/.venv/bin/python" "$ROOT/training/scripts/prune_channels.py" \
  --config "$ROOT/training/configs/pruning_candidate_txn_w1p8_20260806.yaml" \
  --student-config "$ROOT/training/configs/student_candidate_txn_w1p8_20260806.yaml" \
  --allow-dense-fallback \
  --report "$REPORT_ROOT/prune_plan.json"

"$ROOT/.venv/bin/python" "$ROOT/training/scripts/quantize_int8.py" \
  --config "$ROOT/training/configs/quantization_candidate_txn_w1p8_20260806.yaml" \
  --report "$REPORT_ROOT/quantize.json"

"$ROOT/.venv/bin/python" "$ROOT/training/scripts/verify_tflite.py" \
  --config "$ROOT/training/configs/quantization_candidate_txn_w1p8_20260806.yaml" \
  --keras "$ARTIFACT/sms_bytecnn_pruned.keras" \
  --tflite "$ARTIFACT/sms_bytecnn_int8.tflite" \
  --test "$ROOT/training/data/processed_transaction_ad_boundary_arbitration_20260806_r1/validation.jsonl" \
  --quant-report "$REPORT_ROOT/quantize.json"

"$ROOT/.venv/bin/python" "$ROOT/training/scripts/export_android_assets.py" \
  --model "$ARTIFACT/sms_bytecnn_int8.tflite" \
  --dest "$ROOT/android/classifier-sdk/src/main/assets" \
  --quantization INT8

echo "FORMAL_GATE_CHAIN_DONE run=$RUN"
