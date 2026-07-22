#!/usr/bin/env python3
"""Apply leftover agent fixes from _fix_id_yudiwbs.json."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ANN = Path(
    r"C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"
    r"\training\data\interim\annotation"
)
CSV_PATH = ANN / "id_yudiwbs_all_suggested.csv"
FIX_PATH = ANN / "_fix_id_yudiwbs.json"
VALID = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}


def main() -> None:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig", newline="")))
    fields = list(rows[0].keys())
    by = {r["id"]: r for r in rows}
    changes = json.loads(FIX_PATH.read_text(encoding="utf-8")).get("changes", [])

    applied = []
    for c in changes:
        rid, new = c.get("id"), c.get("new")
        if not rid or new not in VALID:
            continue
        r = by.get(rid)
        if not r:
            continue
        old = (r.get("label") or "").strip()
        print(
            f"{rid} agent {c.get('old')}->{new} | cur={old} | "
            f"{(r.get('text') or '')[:90].replace(chr(10), ' ')}"
        )
        if old == new:
            continue
        r["label"] = new
        note = (r.get("notes") or "").strip()
        fix = f"[fix:{old}->{new}] {c.get('reason', '')}"
        r["notes"] = (note + " | " + fix).strip(" |") if note else fix
        if "label_reason" in r:
            r["label_reason"] = c.get("reason", "")
        if not (r.get("annotator") or "").strip():
            r["annotator"] = "audit_fixpass_id"
        applied.append({"id": rid, "old": old, "new": new, "reason": c.get("reason")})

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print("applied", len(applied), applied)
    print("dist", dict(Counter((r.get("label") or "").strip() for r in rows)))


if __name__ == "__main__":
    main()
