#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SOURCE="/mnt/c/dev/Android_SMS_Classifier/training/scripts"
"$ROOT/.venv/bin/python" -m py_compile "$SOURCE/prepare_ai_annotation_run.py" "$SOURCE/finalize_ai_annotation_run.py"
echo "annotation_script_compile=PASS"
