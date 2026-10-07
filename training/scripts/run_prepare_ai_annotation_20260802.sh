#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SOURCE="/mnt/c/dev/Android_SMS_Classifier/training/scripts/prepare_ai_annotation_run.py"
TARGET="$ROOT/training/scripts/prepare_ai_annotation_run.py"

if [[ ! -f "$SOURCE" ]]; then
  echo "Missing current generator: $SOURCE" >&2
  exit 1
fi
cp "$SOURCE" "$TARGET"
exec "$ROOT/.venv/bin/python" "$TARGET" --run-id ai_annotation_20260802_r1 --batch-size 40
