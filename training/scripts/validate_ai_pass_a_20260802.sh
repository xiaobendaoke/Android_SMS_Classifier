#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
OUT="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1"
ROOT="$ROOT" OUT="$OUT" "$ROOT/.venv/bin/python" - <<'PY'
import csv
import json
import os
from pathlib import Path

root = Path(os.environ["ROOT"]); out = Path(os.environ["OUT"])
manifest = json.loads((out / "automated_annotation_manifest.json").read_text(encoding="utf-8"))
expected = set()
for key_name, rel in (("review_group_id", "data/interim/annotation/label_conflicts_v2/blind_annotator_A.csv"), ("review_id", "data/interim/annotation/transaction_specialist_v2/specialist_annotator_A.csv")):
    with (root / "training" / rel).open("r", encoding="utf-8-sig", newline="") as handle:
        expected.update(((row[key_name] or "").strip(), (row["id"] or "").strip()) for row in csv.DictReader(handle))
valid, unknown, malformed, retry = set(), set(), 0, set()
for call in manifest["calls"]:
    if call["pass"] != "a": continue
    status = out / "status" / f"{call['slug']}.txt"
    if not status.exists() or "exit_code=0" not in status.read_text(encoding="utf-8"):
        raise SystemExit(f"failed call: {call['slug']}")
    for line in (out / "stdout" / f"{call['slug']}.txt").read_text(encoding="utf-8").splitlines():
        try: value = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1; continue
        if not isinstance(value, dict) or not {"review_key", "id", "label", "notes"}.issubset(value):
            malformed += 1; continue
        pair = (str(value["review_key"]).strip(), str(value["id"]).strip())
        if pair not in expected:
            unknown.add(pair); continue
        if call.get("format_repair"):
            retry.add(pair)
        valid.add(pair)
missing = expected - valid
result = {"expected": len(expected), "valid": len(valid), "missing": len(missing), "unknown_pairs": len(unknown), "malformed_lines": malformed, "retry_valid": len(retry), "pass": not missing and bool(retry)}
(out / "pass_a_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
raise SystemExit(0 if result["pass"] else 1)
PY
