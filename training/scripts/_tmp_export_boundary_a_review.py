#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(r"C:\dev\Android_SMS_Classifier")
src = ROOT / "training/data/interim/annotation/boundary_v1/boundary_annotator_A.csv"
out_dir = ROOT / "training/data/interim/annotation/boundary_v1/_a_review"
out_dir.mkdir(parents=True, exist_ok=True)

with src.open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

# Split into chunks of 50 for readable review files.
chunk = 50
for start in range(0, len(rows), chunk):
    part = rows[start : start + chunk]
    out = out_dir / f"chunk_{start + 1:03d}_{start + len(part):03d}.txt"
    lines = []
    for i, row in enumerate(part, start=start + 1):
        text = (row.get("text") or "").replace("\r\n", "\n").replace("\r", "\n")
        text = text.replace("\n", "⏎")
        lines.append(f"{i}|{row['id']}|{text}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

meta = {
    "rows": len(rows),
    "cols": list(rows[0].keys()) if rows else [],
    "label_empty": sum(1 for r in rows if not (r.get("label") or "").strip()),
}
(out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
print(meta)
