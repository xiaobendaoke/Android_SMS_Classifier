#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_overlay_length_buckets_20260803_r1"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/${RUN}_export"
mkdir -p "$TARGET"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/analyze_xfyun_overlay_length_buckets.py "$ROOT/training/scripts/analyze_xfyun_overlay_length_buckets.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/analyze_xfyun_overlay_length_buckets.py" --model "$ROOT/training/artifacts/experiments/stage2_xfyun_overlay_txn_weight_1p4_20260803_r1/sms_bytecnn_fp32.keras" --validation "$ROOT/training/data/processed_xfyun_ai_annotation_20260802_r1/validation.jsonl" --output "$TARGET/analysis.json"
