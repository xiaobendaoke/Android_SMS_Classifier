#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SOURCE="/mnt/c/dev/Android_SMS_Classifier/training/scripts"
cp "$SOURCE/prepare_ai_annotation_run.py" "$ROOT/training/scripts/prepare_ai_annotation_run.py"
cp "$SOURCE/prepare_ai_pass_a_format_repair.py" "$ROOT/training/scripts/prepare_ai_pass_a_format_repair.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/prepare_ai_pass_a_format_repair.py"
