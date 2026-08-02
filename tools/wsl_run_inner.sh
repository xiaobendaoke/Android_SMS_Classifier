#!/usr/bin/env bash
# Copy a script from the Windows ASCII junction into the WSL ASCII tree, then run it.
set -eu

REL="${1:?usage: wsl_run_inner.sh <rel/path/script.sh>}"
REL="${REL#./}"
REL="${REL#/}"

WIN_ROOT="/mnt/c/dev/Android_SMS_Classifier"
WSL_ROOT="${WSL_RUN_ROOT:-/home/colab/projects/Android_SMS_Classifier}"

SRC="$WIN_ROOT/$REL"
DST="$WSL_ROOT/$REL"

if [[ ! -f "$SRC" ]]; then
  echo "SOURCE_MISSING: $SRC" >&2
  echo "Ensure the Windows junction exists: C:\\dev\\Android_SMS_Classifier" >&2
  exit 1
fi

mkdir -p "$(dirname "$DST")"
cp -f "$SRC" "$DST"
# Normalize CRLF / UTF-8 BOM if the file was edited on Windows.
sed -i 's/\r$//' "$DST" || true
sed -i '1s/^\xEF\xBB\xBF//' "$DST" || true
chmod +x "$DST" || true
cd "$WSL_ROOT"
exec bash "$DST"
