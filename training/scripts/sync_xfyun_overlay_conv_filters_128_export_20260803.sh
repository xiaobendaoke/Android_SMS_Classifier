#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="stage2_xfyun_overlay_conv_filters_128_20260803_r1"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/${RUN}_export"

mkdir -p "$TARGET"
cp "$ROOT/training/artifacts/experiments/$RUN/config.yaml" "$TARGET/config.yaml"
cp "$ROOT/training/artifacts/experiments/$RUN/distill_manifest.json" "$TARGET/distill_manifest.json"
cp "$ROOT/training/reports/experiments/$RUN/experiment.json" "$TARGET/experiment.json"
