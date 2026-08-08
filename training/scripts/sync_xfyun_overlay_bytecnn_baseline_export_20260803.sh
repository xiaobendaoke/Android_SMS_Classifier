#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_overlay_bytecnn_hard_20260803_r1"
SOURCE_REPORT="$ROOT/training/reports/experiments/$RUN/experiment.json"
SOURCE_CONFIG="$ROOT/training/artifacts/experiments/$RUN/config.yaml"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/${RUN}_export"
mkdir -p "$TARGET"
cp "$SOURCE_REPORT" "$TARGET/experiment.json"
cp "$SOURCE_CONFIG" "$TARGET/config.yaml"
