#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SOURCE="/mnt/c/dev/Android_SMS_Classifier/training/scripts"
cp "$SOURCE/prepare_ai_annotation_run.py" "$ROOT/training/scripts/prepare_ai_annotation_run.py"
cp "$SOURCE/repair_ai_annotation_runners.py" "$ROOT/training/scripts/repair_ai_annotation_runners.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/repair_ai_annotation_runners.py" --run-id ai_annotation_20260802_r1
