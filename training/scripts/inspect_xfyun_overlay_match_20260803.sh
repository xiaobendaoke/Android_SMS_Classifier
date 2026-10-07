#!/usr/bin/env bash
set -euo pipefail
ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
OUT="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1/direct_xfyun_pass_c_20260803"
ROOT="$ROOT" OUT="$OUT" "$ROOT/.venv/bin/python" - <<'PY'
import json, os
from pathlib import Path
root=Path(os.environ["ROOT"]); out=Path(os.environ["OUT"])
c={x["id"] for x in json.loads((out/"automated_label_corrections_ai_annotation_20260802_r1.json").read_text(encoding="utf-8"))["corrections"]}
for name in ("processed", "processed_v2"):
    ids=set(); split={}
    for part in ("train","validation","test"):
        path=root/"training"/"data"/name/f"{part}.jsonl"
        if path.exists():
            part_ids={json.loads(line)["id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
            ids |= part_ids; split[part]=len(c & part_ids)
    print(json.dumps({"source":name,"matched":len(c&ids),"unmatched":len(c-ids),"by_split":split},ensure_ascii=False))
PY
