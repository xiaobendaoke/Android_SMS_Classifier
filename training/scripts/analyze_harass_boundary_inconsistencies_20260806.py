#!/usr/bin/env python3
"""Identify inconsistent template groups in the fixed data for HARASS boundary arbitration."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed_xfyun_carrier_repayment_relabel_20260804_r1"


def load_records(path):
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def main():
    train = load_records(DATA / "train.jsonl")
    val = load_records(DATA / "validation.jsonl")
    all_records = train + val

    groups = defaultdict(list)
    for r in all_records:
        tg = r.get("template_group", "")
        if tg:
            groups[tg].append(r)

    inconsistent = {}
    consistent_count = 0
    for tg, rows in groups.items():
        labels = set(r["label"] for r in rows if r["label"] != "NEEDS_REVIEW")
        if len(labels) > 1:
            inconsistent[tg] = {"labels": sorted(labels), "row_count": len(rows), "split": rows[0].get("split", "")}
        else:
            consistent_count += 1

    harass_involved = {tg: info for tg, info in inconsistent.items() if "HARASS" in info["labels"]}

    total_inconsistent_rows = sum(info["row_count"] for info in inconsistent.values())
    harass_inconsistent_rows = sum(info["row_count"] for info in harass_involved.values())

    pair_counts = defaultdict(int)
    for info in inconsistent.values():
        pair = "|".join(info["labels"])
        pair_counts[pair] += 1

    report = {
        "total_template_groups": len(groups),
        "consistent_groups": consistent_count,
        "inconsistent_groups": len(inconsistent),
        "harass_involved_inconsistent_groups": len(harass_involved),
        "total_inconsistent_rows": total_inconsistent_rows,
        "harass_inconsistent_rows": harass_inconsistent_rows,
        "inconsistent_label_pair_counts": dict(sorted(pair_counts.items(), key=lambda x: -x[1])),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    report_dir = ROOT / "reports" / "experiments" / "harass_boundary_inconsistency_analysis_20260806_r1"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
