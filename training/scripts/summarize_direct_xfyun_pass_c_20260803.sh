#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
OUT="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1/direct_xfyun_pass_c_20260803"
OUT="$OUT" "$ROOT/.venv/bin/python" - <<'PY'
import json
import os
from pathlib import Path

out = Path(os.environ["OUT"])
manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
summary = {"calls": len(manifest["calls"]), "status_ok": 0, "status_failed": 0, "status_missing": 0, "stdout_present": 0}
for call in manifest["calls"]:
    slug = call["slug"]
    status = out / "status" / f"{slug}.txt"
    stdout = out / "stdout" / f"{slug}.txt"
    summary["stdout_present"] += int(stdout.exists())
    if not status.exists(): summary["status_missing"] += 1
    elif "exit_code=0" in status.read_text(encoding="utf-8"): summary["status_ok"] += 1
    else: summary["status_failed"] += 1
print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
PY
