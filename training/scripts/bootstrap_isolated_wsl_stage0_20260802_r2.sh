#!/usr/bin/env bash
set -euo pipefail

RUN_ID="stage0_baseline_20260802_r2"
SOURCE="/mnt/c/dev/Android_SMS_Classifier"
DESTINATION="/home/colab/projects/Android_SMS_Classifier_${RUN_ID}"
LEGACY_VENV="/home/colab/projects/Android_SMS_Classifier/.venv"

if [[ -e "$DESTINATION" ]]; then
  echo "Refusing to overwrite existing isolated worktree: $DESTINATION" >&2
  exit 2
fi
if [[ ! -d "$SOURCE/.git" ]]; then
  echo "Missing ASCII source worktree: $SOURCE" >&2
  exit 1
fi
if [[ ! -x "$LEGACY_VENV/bin/python" ]]; then
  echo "Missing reusable WSL virtual environment: $LEGACY_VENV" >&2
  exit 1
fi

git clone --no-hardlinks "$SOURCE" "$DESTINATION"
for rel in training/data/raw training/data/interim training/data/processed training/data/processed_v2 training/artifacts/student; do
  if [[ -e "$SOURCE/$rel" ]]; then
    mkdir -p "$DESTINATION/$(dirname "$rel")"
    cp -a "$SOURCE/$rel" "$DESTINATION/$(dirname "$rel")/"
  fi
done
ln -s "$LEGACY_VENV" "$DESTINATION/.venv"

mkdir -p "$DESTINATION/training/reports/experiments/$RUN_ID"
{
  printf '{\n'
  printf '  "run_id": "%s",\n' "$RUN_ID"
  printf '  "source": "%s",\n' "$SOURCE"
  printf '  "head": "%s",\n' "$(git -C "$DESTINATION" rev-parse HEAD)"
  printf '  "network_used": false,\n'
  printf '  "locked_test_model_metrics_read": false,\n'
  printf '  "copied_inputs": ["raw", "interim", "processed", "processed_v2", "artifacts/student"]\n'
  printf '}\n'
} >"$DESTINATION/training/reports/experiments/$RUN_ID/worktree_setup.json"
git -C "$DESTINATION" status --short --branch
printf 'isolated_root=%s\n' "$DESTINATION"
