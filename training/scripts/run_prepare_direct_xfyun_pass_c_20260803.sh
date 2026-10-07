#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SOURCE="/mnt/c/dev/Android_SMS_Classifier/training/scripts"
cp "$SOURCE/direct_xfyun_call.py" "$ROOT/training/scripts/direct_xfyun_call.py"
cp "$SOURCE/prepare_direct_xfyun_pass_c.py" "$ROOT/training/scripts/prepare_direct_xfyun_pass_c.py"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/prepare_direct_xfyun_pass_c.py"
