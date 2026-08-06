#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$HOME/projects/Android_SMS_Classifier}"
WIN_ROOT="/mnt/c/dev/Android_SMS_Classifier"

if [[ ! -d "$WIN_ROOT" ]]; then
  echo "ERROR: Windows ASCII junction missing at $WIN_ROOT" >&2
  exit 1
fi

mkdir -p "$ROOT"
rsync -a \
  --exclude 'data/' \
  --exclude 'artifacts/' \
  --exclude '.venv/' \
  --exclude '**/__pycache__/' \
  --exclude '.pytest_cache/' \
  "$WIN_ROOT/training/" "$ROOT/training/"
rsync -a \
  --exclude '.venv/' \
  --exclude '**/__pycache__/' \
  "$WIN_ROOT/tools/" "$ROOT/tools/"
echo "SYNC_OK"
