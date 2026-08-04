#!/usr/bin/env python3
"""Validate local-only A/B blind relabel outputs and write a safe summary."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = "xfyun_error_relabel_20260803_r1"
PACK = ROOT / "data/interim/annotation" / RUN
REPORT = ROOT / "reports/experiments" / RUN
LABELS = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}


def parse(name: str) -> dict[str, dict[str, str]]:
    expected = {json.loads(line)["id"] for line in (PACK / f"{name}_blind.jsonl").read_text(encoding="utf-8").splitlines() if line}
    rows: dict[str, dict[str, str]] = {}
    malformed = 0
    for line in (PACK / f"{name}_raw.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            malformed += 1
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        item_id, label, notes = row.get("id"), row.get("label"), row.get("notes")
        if item_id in expected and label in LABELS and isinstance(notes, str) and notes.strip():
            rows[item_id] = {"label": label, "notes_present": True}
        else:
            malformed += 1
    return {"rows": rows, "expected": expected, "malformed": malformed}


def main() -> int:
    a, b = parse("pass_a"), parse("pass_b")
    common = sorted(set(a["rows"]) & set(b["rows"]))
    conflicts = [item for item in common if a["rows"][item]["label"] != b["rows"][item]["label"]]
    c_rows, c_malformed = {}, 0
    if conflicts:
        for line in (PACK / "pass_c_raw.txt").read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("{"):
                c_malformed += 1
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                c_malformed += 1
                continue
            if row.get("id") in conflicts and row.get("label") in LABELS and isinstance(row.get("notes"), str) and row["notes"].strip():
                c_rows[row["id"]] = row["label"]
            else:
                c_malformed += 1
    final = {item: (c_rows[item] if item in c_rows else a["rows"][item]["label"]) for item in common}
    payload = {"run_id": RUN, "status": "PROVISIONAL_AUTOMATED_MULTI_PASS" if len(c_rows) == len(conflicts) else "PROVISIONAL_AUTOMATED_MULTI_PASS_QA_FAILED", "claim_allowed": False, "human_verified": False, "formal_acceptance_allowed": False, "locked_test_read": False, "pass_a": {"expected": len(a["expected"]), "valid": len(a["rows"]), "missing": len(a["expected"] - set(a["rows"])), "malformed": a["malformed"], "label_counts": dict(Counter(row["label"] for row in a["rows"].values()))}, "pass_b": {"expected": len(b["expected"]), "valid": len(b["rows"]), "missing": len(b["expected"] - set(b["rows"])), "malformed": b["malformed"], "label_counts": dict(Counter(row["label"] for row in b["rows"].values()))}, "pass_c": {"expected": len(conflicts), "valid": len(c_rows), "missing": len(set(conflicts) - set(c_rows)), "malformed": c_malformed, "label_counts": dict(Counter(c_rows.values()))}, "agreement": {"common_valid": len(common), "conflict_count": len(conflicts), "conflict_ids": conflicts, "exact_agreement": (len(common) - len(conflicts)) / len(common) if common else 0.0}, "final_label_counts": dict(Counter(final.values()))}
    (REPORT / "qa_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
