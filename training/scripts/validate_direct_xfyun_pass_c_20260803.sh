#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
OUT="$ROOT/training/data/interim/annotation/automated_runs/ai_annotation_20260802_r1"
OUT="$OUT" "$ROOT/.venv/bin/python" - <<'PY'
import json
import os
from pathlib import Path

out = Path(os.environ["OUT"])
direct = out / "direct_xfyun_pass_c_20260803"
allowed = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}
expected = set()
for prompt in sorted((out / "prompts").glob("c_*.txt")):
    marker = "CONFLICT RECORDS:\n"
    payload = prompt.read_text(encoding="utf-8").split(marker, 1)[1]
    expected.update((str(row["review_key"]), str(row["id"])) for row in json.loads(payload))
valid, duplicates, unknown = {}, 0, 0
malformed = 0
for stdout in sorted((direct / "stdout").glob("c_*.txt")):
    for line in stdout.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            malformed += int(bool(line.strip()))
            continue
        if not isinstance(row, dict) or not {"review_key", "id", "label", "notes"}.issubset(row):
            malformed += 1
            continue
        key = (str(row["review_key"]).strip(), str(row["id"]).strip())
        if key not in expected:
            unknown += 1
        elif key in valid:
            duplicates += 1
        elif str(row["label"]).strip() not in allowed or not str(row["notes"]).strip():
            malformed += 1
        else:
            valid[key] = {field: str(row[field]).strip() for field in ("review_key", "id", "label", "notes")}
result = {"expected": len(expected), "valid": len(valid), "missing": len(expected - set(valid)), "duplicates": duplicates, "unknown": unknown, "malformed_lines": malformed, "pass": len(valid) == len(expected) and not duplicates and not unknown}
(direct / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
raise SystemExit(0 if result["pass"] else 1)
PY
