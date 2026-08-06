#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SRC="/mnt/c/dev/Android_SMS_Classifier/training"
RUN="stage2_xfyun_txn_ad_overlay_lr_5e4_hard_boundary_both_1p5_txn_w1p8_formalgate_20260806_r1"
ARTIFACT="$ROOT/training/artifacts/experiments/$RUN"

cp -f "$SRC/scripts/export_android_assets.py" "$ROOT/training/scripts/export_android_assets.py"
export PYTHONPATH="$ROOT/training"

"$ROOT/.venv/bin/python" "$ROOT/training/scripts/export_android_assets.py" \
  --model "$ARTIFACT/sms_bytecnn_int8.tflite" \
  --dest "$ROOT/android/classifier-sdk/src/main/assets" \
  --quantization INT8

echo "EXPORT_DONE run=$RUN"
