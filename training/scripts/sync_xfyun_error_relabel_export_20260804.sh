#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="xfyun_error_relabel_20260803_r1"
TARGET="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/${RUN}_export"
mkdir -p "$TARGET"
cp "$ROOT/training/reports/experiments/$RUN/call_manifest.json" "$TARGET/call_manifest.json"
cp "$ROOT/training/reports/experiments/$RUN/qa_summary.json" "$TARGET/qa_summary.json"
cp "$ROOT/training/reports/experiments/$RUN/overlay_summary.json" "$TARGET/overlay_summary.json"
