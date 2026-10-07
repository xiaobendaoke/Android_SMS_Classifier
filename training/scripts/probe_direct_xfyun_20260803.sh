#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
OUT="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1/direct_xfyun_probe_20260803"
mkdir -p "$OUT"
printf '%s\n' 'Reply exactly: ok' > "$OUT/prompt.txt"
set +e
"$ROOT/.venv/bin/python" "$ROOT/training/scripts/direct_xfyun_call.py" --demo-config /mnt/c/Users/woshinibaba/AppData/Local/Temp/opencode/xf_demo.py --model xopdeepseekv4flash --prompt "$OUT/prompt.txt" --timeout 60 > "$OUT/stdout.txt" 2> "$OUT/stderr.txt"
RC=$?
set -e
printf '{"transport":"direct_openai_sdk_xfyun_v2","exit_code":%s,"stdout_bytes":%s,"stderr_bytes":%s}\n' "$RC" "$(wc -c < "$OUT/stdout.txt")" "$(wc -c < "$OUT/stderr.txt")"
exit "$RC"
