#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SOURCE="$ROOT/training/data/processed_xfyun_ai_annotation_20260802_r1/manifest.json"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/xfyun_overlay_ai_annotation_20260802_r1_export"
mkdir -p "$TARGET"
cp "$SOURCE" "$TARGET/manifest.json"
