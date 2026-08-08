#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}"
cp /mnt/c/dev/Android_SMS_Classifier/tools/probe_sample_eval_20260808.py "$ROOT/tools/probe_sample_eval_20260808.py"
exec "$ROOT/.venv/bin/python" "$ROOT/tools/probe_sample_eval_20260808.py"
