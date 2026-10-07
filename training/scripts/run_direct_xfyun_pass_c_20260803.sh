#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
exec bash "$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1/direct_xfyun_pass_c_20260803/run_all.sh"
