#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
OUT="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1"
if [[ ! -d "$OUT" ]]; then
  echo "MISSING"
  exit 0
fi
printf 'manifest='
test -f "$OUT/automated_annotation_manifest.json" && echo present || echo missing
printf 'prompts='
find "$OUT/prompts" -type f -name '*.txt' 2>/dev/null | wc -l
printf 'runners='
find "$OUT/runners" -type f -name '*.sh' 2>/dev/null | wc -l
printf 'pass_a='
test -f "$OUT/run_pass_a.sh" && echo present || echo missing
printf 'pass_b='
test -f "$OUT/run_pass_b.sh" && echo present || echo missing
if [[ -f "$OUT/automated_annotation_manifest.json" ]]; then
  "$ROOT/.venv/bin/python" -c 'import json,sys; p=json.load(open(sys.argv[1], encoding="utf-8")); print(json.dumps({"run_id":p["run_id"],"status":p["status"],"calls":len(p["calls"]),"pass_a":sum(x["pass"]=="a" for x in p["calls"]),"pass_b":sum(x["pass"]=="b" for x in p["calls"]),"claim_allowed":p["claim_allowed"]}, ensure_ascii=False))' "$OUT/automated_annotation_manifest.json"
fi
