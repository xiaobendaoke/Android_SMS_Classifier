#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/prepare_xfyun_provisional_overlay.py "$ROOT/training/scripts/prepare_xfyun_provisional_overlay.py"
"$ROOT/.venv/bin/python" "$ROOT/training/scripts/prepare_xfyun_provisional_overlay.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/apply_automated_terra_overlay.py" --overlay "$ROOT/training/data/interim/annotation/xfyun_overlay_ai_annotation_20260802_r1.json" --source "$ROOT/training/data/processed_v2" --output "$ROOT/training/data/processed_xfyun_ai_annotation_20260802_r1" --quarantine "$ROOT/training/data/interim/quarantine/train_quarantine_xfyun_ai_annotation_20260802_r1.jsonl"
