#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SOURCE="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1/direct_xfyun_pass_c_20260803"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/ai_annotation_20260802_r1_direct_xfyun_export"
mkdir -p "$TARGET"
cp "$SOURCE/manifest.json" "$TARGET/direct_transport_manifest.json"
cp "$SOURCE/automated_annotation_manifest.json" "$TARGET/automated_annotation_manifest.json"
cp "$SOURCE/automated_annotation_report.json" "$TARGET/automated_annotation_report.json"
cp "$SOURCE/automated_label_corrections_ai_annotation_20260802_r1.json" "$TARGET/automated_label_corrections_ai_annotation_20260802_r1.json"
cp "$SOURCE/validation.json" "$TARGET/pass_c_validation.json"
