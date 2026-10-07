#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
OUT="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1"
OUT="$OUT" "$ROOT/.venv/bin/python" - <<'PY'
import json, os
from pathlib import Path
out = Path(os.environ["OUT"])
manifest = json.loads((out / "automated_annotation_manifest.json").read_text(encoding="utf-8"))
calls = [c for c in manifest["calls"] if c["pass"] == "b"]
summary = {"calls": len(calls), "status_ok": 0, "json_rows": 0, "expected_rows": sum(c["count"] for c in calls), "invalid_json_lines": 0, "invalid_schema_rows": 0, "missing_outputs": 0, "invalid_line_kinds": {}}
for call in calls:
    status = out / "status" / f"{call['slug']}.txt"; stdout = out / "stdout" / f"{call['slug']}.txt"
    if status.exists() and "exit_code=0" in status.read_text(encoding="utf-8"): summary["status_ok"] += 1
    if not stdout.exists(): summary["missing_outputs"] += 1; continue
    for line in stdout.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try: value = json.loads(line)
        except json.JSONDecodeError:
            summary["invalid_json_lines"] += 1
            s=line.strip(); kind="fence" if s.startswith("```") else ("json_prefix_malformed" if s.startswith("{") else "other_non_json")
            summary["invalid_line_kinds"][kind]=summary["invalid_line_kinds"].get(kind,0)+1; continue
        if not isinstance(value, dict) or not {"review_key","id","label","notes"}.issubset(value): summary["invalid_schema_rows"] += 1
        else: summary["json_rows"] += 1
print(json.dumps(summary, ensure_ascii=False))
PY
