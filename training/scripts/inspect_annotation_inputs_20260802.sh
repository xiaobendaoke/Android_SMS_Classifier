#!/usr/bin/env bash
set -euo pipefail

ROOT="${WSL_RUN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
ROOT="$ROOT" "$ROOT/.venv/bin/python" - <<'PY'
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

root = Path(os.environ["ROOT"])
paths = {
    "label_conflicts_a": root / "training/data/interim/annotation/label_conflicts_v2/blind_annotator_A.csv",
    "label_conflicts_b": root / "training/data/interim/annotation/label_conflicts_v2/blind_annotator_B.csv",
    "transaction_specialist_a": root / "training/data/interim/annotation/transaction_specialist_v2/specialist_annotator_A.csv",
    "transaction_specialist_b": root / "training/data/interim/annotation/transaction_specialist_v2/specialist_annotator_B.csv",
}
for name, path in paths.items():
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    keys = [row.get("review_group_id") or row.get("review_id") for row in rows]
    print(json.dumps({
        "name": name,
        "exists": path.exists(),
        "count": len(rows),
        "fields": list(rows[0]) if rows else [],
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "labels_blank": all(not row.get("label") for row in rows),
        "notes_blank": all(not row.get("notes") for row in rows),
        "annotators_blank": all(not row.get("human_annotator_id") for row in rows),
        "unique_keys": len(set(keys)),
    }, ensure_ascii=False))
PY
