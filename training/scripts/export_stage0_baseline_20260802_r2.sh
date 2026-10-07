#!/usr/bin/env bash
set -euo pipefail

RUN_ID="stage0_baseline_20260802_r2"
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
SOURCE="$ROOT/training/reports/experiments/$RUN_ID"
DESTINATION="/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments/${RUN_ID}_export"

if [[ ! -d "$SOURCE" ]]; then
  echo "Missing run output: $SOURCE" >&2
  exit 1
fi
if [[ -e "$DESTINATION" ]]; then
  echo "Refusing to overwrite existing export: $DESTINATION" >&2
  exit 2
fi

mkdir -p "$DESTINATION"
cp -R "$SOURCE"/. "$DESTINATION"/
find "$DESTINATION" -type f -print0 | sort -z | xargs -0 sha256sum >"$DESTINATION/output_sha256s.txt"
printf 'source_run_id=%s\nsource_root=%s\n' "$RUN_ID" "$ROOT" >"$DESTINATION/sync_provenance.txt"
