#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_overlay_pipeline_20260803_r1"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/${RUN}_export"
mkdir -p "$TARGET"
cp "$ROOT/training/reports/experiments/$RUN/evaluate.json" "$TARGET/evaluate.json"
