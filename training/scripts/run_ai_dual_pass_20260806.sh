#!/usr/bin/env bash
set -u -o pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="$ROOT/training/data/interim/annotation/ai_dual_pass_20260806_r1"

if [[ ! -f "$RUN/run_all.sh" ]]; then
  echo "Missing prepared run: $RUN" >&2
  exit 1
fi

exec bash "$RUN/run_all.sh"
