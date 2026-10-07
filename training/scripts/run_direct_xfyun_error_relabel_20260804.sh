#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
cp /mnt/c/dev/Android_SMS_Classifier/training/scripts/run_direct_xfyun_error_relabel.py "$ROOT/training/scripts/run_direct_xfyun_error_relabel.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/run_direct_xfyun_error_relabel.py"
