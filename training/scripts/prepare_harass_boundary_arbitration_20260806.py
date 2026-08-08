#!/usr/bin/env python3
"""Prepare blind arbitration packs for inconsistent template groups."""
from __future__ import annotations

import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "processed_xfyun_carrier_repayment_relabel_20260804_r1"
RUN = "harass_boundary_arbitration_20260806_r1"
PACK = ROOT / "data" / "interim" / "annotation" / RUN
REPORT_WIN = Path("/mnt/c/dev/Android_SMS_Classifier/training/reports/experiments") / RUN

EXPECTED_SHA = {
    "train": "0777cae6ef9681ffea48d1eaf74d7f582aeed49719a200eb62a453195d807fa0",
    "validation": "4ff8e9ea6698c6098f95e997f5d0b378ddd75673eb1084e261bcb182d032a64f",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def main() -> int:
    if PACK.exists() or REPORT_WIN.exists():
        raise SystemExit(f"refusing to overwrite run_id: {RUN}")
    for name in ("train", "validation"):
        actual = sha256(DATA / f"{name}.jsonl")
        if actual != EXPECTED_SHA[name]:
            raise SystemExit(f"{name} SHA mismatch: {actual}")

    records = load_records(DATA / "train.jsonl") + load_records(DATA / "validation.jsonl")
    groups = defaultdict(list)
    for r in records:
        tg = r.get("template_group", "")
        if tg:
            groups[tg].append(r)

    inconsistent = {}
    for tg, rows in groups.items():
        labels = {r["label"] for r in rows if r["label"] != "NEEDS_REVIEW"}
        if len(labels) > 1:
            inconsistent[tg] = sorted(labels)

    candidates = sorted(
        (r for tg in inconsistent for r in groups[tg]),
        key=lambda r: r["id"],
    )
    if not candidates:
        raise SystemExit("no inconsistent template groups found")

    rows = [
        {
            "review_key": hashlib.sha256((RUN + r["id"]).encode()).hexdigest()[:16],
            "id": r["id"],
            "text": r["text"],
        }
        for r in candidates
    ]
    pass_b_rows = random.Random(20260806).sample(rows, len(rows))

    PACK.mkdir(parents=True)
    REPORT_WIN.mkdir(parents=True)
    (PACK / "pass_a_blind.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    (PACK / "pass_b_blind.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in pass_b_rows),
        encoding="utf-8",
    )

    pair_counts = Counter("|".join(labels) for labels in inconsistent.values())
    manifest = {
        "run_id": RUN,
        "status": "PENDING_EXTERNAL_APPROVAL",
        "claim_allowed": False,
        "human_verified": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "source_data_sha256": {name: EXPECTED_SHA[name] for name in ("train", "validation")},
        "candidate_selection": "inconsistent_template_groups_only",
        "inconsistent_template_group_count": len(inconsistent),
        "harass_involved_inconsistent_group_count": sum(
            1 for labels in inconsistent.values() if "HARASS" in labels
        ),
        "inconsistent_label_pair_counts": dict(
            sorted(pair_counts.items(), key=lambda x: -x[1])
        ),
        "candidate_count": len(rows),
        "split_membership_preserved": True,
        "blind_fields": ["review_key", "id", "text"],
        "excluded_fields": [
            "prior_label",
            "model_prediction",
            "split",
            "annotator_ids",
        ],
        "pass_a_sha256": sha256(PACK / "pass_a_blind.jsonl"),
        "pass_b_sha256": sha256(PACK / "pass_b_blind.jsonl"),
        "privacy": {
            "raw_sms_text_committed": False,
            "raw_sample_ids_committed": False,
            "raw_ai_outputs_committed": False,
        },
    }
    (REPORT_WIN / "preparation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: manifest[key]
                for key in (
                    "run_id",
                    "inconsistent_template_group_count",
                    "candidate_count",
                    "pass_a_sha256",
                    "pass_b_sha256",
                )
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
