#!/usr/bin/env bash
set -euo pipefail

RUN_ID="stage0_baseline_20260802"
WSL_ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
WIN_ROOT="/mnt/c/dev/Android_SMS_Classifier"
SOURCE="$WSL_ROOT/training/reports/experiments/$RUN_ID"
DESTINATION="$WIN_ROOT/training/reports/experiments/${RUN_ID}_export"

if [[ ! -d "$SOURCE" ]]; then
  echo "Missing WSL report directory: $SOURCE" >&2
  exit 1
fi
if [[ -e "$DESTINATION" ]]; then
  echo "Refusing to overwrite existing export: $DESTINATION" >&2
  exit 2
fi

mkdir -p "$DESTINATION"
cp -R "$SOURCE"/. "$DESTINATION"/
find "$DESTINATION" -type f -print0 | sort -z | xargs -0 sha256sum >"$DESTINATION/output_sha256s.txt"
printf 'source_run_id=%s\n' "$RUN_ID" >"$DESTINATION/sync_provenance.txt"
printf 'synced_from=%s\n' "$SOURCE" >>"$DESTINATION/sync_provenance.txt"
printf 'synced_at=' >>"$DESTINATION/sync_provenance.txt"
date -u +%Y-%m-%dT%H:%M:%SZ >>"$DESTINATION/sync_provenance.txt"
