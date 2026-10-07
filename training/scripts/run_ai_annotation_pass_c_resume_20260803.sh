#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
OUT="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1"
RUNNER=$(find "$OUT" -maxdepth 1 -type f -name 'run_pass_c_resume_*.sh' -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)
test -n "$RUNNER"
exec bash "$RUNNER"
