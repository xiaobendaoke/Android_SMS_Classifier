#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SOURCE="/mnt/c/dev/Android_SMS_Classifier/training/scripts"
cp "$SOURCE/prepare_ai_annotation_run.py" "$ROOT/training/scripts/prepare_ai_annotation_run.py"
cp "$SOURCE/finalize_ai_annotation_run.py" "$ROOT/training/scripts/finalize_ai_annotation_run.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/finalize_ai_annotation_run.py" prepare-c --run-id ai_annotation_20260802_r1
