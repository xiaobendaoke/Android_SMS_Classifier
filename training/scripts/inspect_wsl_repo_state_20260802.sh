#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
printf 'root=%s\n' "$ROOT"
git -C "$ROOT" status --short --branch
printf '%s\n' '--- head ---'
git -C "$ROOT" rev-parse HEAD
git -C "$ROOT" log -1 --oneline
printf '%s\n' '--- relevant files ---'
for rel in training/scripts/run_recall_v4.py training/scripts/evaluate.py training/scripts/check_split_leakage.py training/scripts/validate_labels.py; do
  if [[ -f "$ROOT/$rel" ]]; then
    sha256sum "$ROOT/$rel"
  else
    printf 'MISSING %s\n' "$rel"
  fi
done
