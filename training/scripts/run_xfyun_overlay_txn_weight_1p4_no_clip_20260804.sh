#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/distill_student.py "$ROOT/training/scripts/distill_student.py"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/run_xfyun_overlay_txn_weight_1p4_no_clip.py "$ROOT/training/scripts/run_xfyun_overlay_txn_weight_1p4_no_clip.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/run_xfyun_overlay_txn_weight_1p4_no_clip.py"
