#!/usr/bin/env bash
set -u -o pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
RUN="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1"
exec bash "$RUN/run_pass_b.sh"
