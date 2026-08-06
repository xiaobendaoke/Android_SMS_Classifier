#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SRC="/mnt/c/dev/Android_SMS_Classifier/training/scripts/analyze_harass_boundary_inconsistencies_20260806.py"
cp -f "$SRC" "$ROOT/training/scripts/analyze_harass_boundary_inconsistencies_20260806.py"
export PYTHONPATH="$ROOT/training"
exec "$ROOT/.venv/bin/python" "$ROOT/training/scripts/analyze_harass_boundary_inconsistencies_20260806.py"
