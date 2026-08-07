#!/usr/bin/env python3
"""Apply user-reviewed AI dual-pass labels to frozen train/validation splits."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parent.parent
RUN_ID_DEFAULT = "ai_dual_pass_20260806_r1"
PASS_A_ID = "AUTO_MOREAI_MINIMAXM3_PASS_A_001"
PASS_B_ID = "AUTO_MOREAI_MINIMAXM3_PASS_B_001"
PASS_C_ID = "AUTO_MOREAI_MINIMAXM3_ADJUDICATOR_001"
REVIEWER_ID = "HUMAN_REVIEWER_001"
ALLOWED = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}
STATUS = "USER_REVIEWED_AI_DUAL_PASS"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> List[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def read_review_csv(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]
    required = {"review_id", "id", "final_label"}
    for row in rows:
        if not required.issubset(row):
            raise SystemExit(f"Review CSV missing columns; got {sorted(row)}")
        label = row["final_label"].upper()
        if label not in ALLOWED:
            raise SystemExit(f"Review row {row['review_id']} has invalid final_label {row['final_label']!r}")
        row["final_label"] = label
    return rows


def transform_record(
    record: dict,
    decisions: Dict[str, dict],
    passed_ids: set[str],
) -> dict:
    record_id = str(record.get("id", ""))
    decision = decisions.get(record_id)
    if decision is None:
        return record
    record = dict(record)
    record["label"] = decision["final_label"]
    annotator_ids = list(record.get("annotator_ids") or [])
    for annotator in (PASS_A_ID, PASS_B_ID, PASS_C_ID, REVIEWER_ID):
        if annotator not in annotator_ids:
            annotator_ids.append(annotator)
    record["annotator_ids"] = annotator_ids
    record["annotation_status"] = STATUS
    record["ai_dual_pass_review_id"] = decision["review_id"]
    record["ai_dual_pass_reviewer"] = REVIEWER_ID
    passed_ids.add(record_id)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--user-review-csv", type=Path, required=True)
    parser.add_argument("--frozen-train", type=Path, default=ROOT / "data/processed_v2/train.jsonl")
    parser.add_argument("--frozen-validation", type=Path, default=ROOT / "data/processed_v2/validation.jsonl")
    parser.add_argument("--frozen-test", type=Path, default=ROOT / "data/processed_v2/test.jsonl")
    parser.add_argument("--out-version", default="processed_ai_dual_pass_20260806_r1")
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    review_rows = read_review_csv(args.user_review_csv)
    decisions: Dict[str, dict] = {}
    for row in review_rows:
        if row["id"] in decisions:
            raise SystemExit(f"Duplicate reviewed id {row['id']}")
        decisions[row["id"]] = row

    test_sha_before = sha256(args.frozen_test)
    out_root = ROOT / "data" / args.out_version
    quarantine_root = ROOT / "data" / "interim" / "quarantine" / args.out_version
    audit_root = ROOT / "reports" / args.out_version
    out_root.mkdir(parents=True, exist_ok=True)
    audit_root.mkdir(parents=True, exist_ok=True)

    summary: dict = {
        "run_id": args.out_version,
        "status": STATUS,
        "claim_allowed": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "reviewer_id": REVIEWER_ID,
        "annotator_ids": [PASS_A_ID, PASS_B_ID, PASS_C_ID],
        "review_row_count": len(review_rows),
        "applied": 0,
        "unmatched_review_ids": [],
        "quarantine_needs_review_ids": [],
        "label_distribution": {},
        "splits": {},
    }
    quarantine: List[dict] = []
    seen_ids: set[str] = set()

    for split_name, frozen_path in (("train", args.frozen_train), ("validation", args.frozen_validation)):
        records = load_jsonl(frozen_path)
        passed: set[str] = set()
        output: List[dict] = []
        changed = 0
        for record in records:
            record_id = str(record.get("id", ""))
            seen_ids.add(record_id)
            old_label = record.get("label")
            transformed = transform_record(record, decisions, passed)
            if transformed is not record:
                changed += 1
                if transformed["label"] == "NEEDS_REVIEW":
                    quarantine.append(transformed)
                    summary["quarantine_needs_review_ids"].append(record_id)
                    continue
            output.append(transformed)
        summary["label_distribution"][split_name] = dict(Counter(row.get("label", "") for row in output))
        out_path = out_root / f"{split_name}.jsonl"
        write_jsonl(out_path, output)
        summary["splits"][split_name] = {
            "path": str(out_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256(out_path),
            "row_count": len(output),
            "changed_count": changed,
        }

    summary["applied"] = sum(1 for record_id in decisions if record_id in seen_ids)
    summary["unmatched_review_ids"] = sorted(
        review["review_id"] for review in review_rows if review["id"] not in seen_ids
    )
    if quarantine:
        quarantine_path = quarantine_root / "needs_review.jsonl"
        write_jsonl(quarantine_path, quarantine)
        summary["quarantine"] = {
            "path": str(quarantine_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256(quarantine_path),
            "row_count": len(quarantine),
        }

    test_path = out_root / "test.jsonl"
    shutil.copyfile(args.frozen_test, test_path)
    summary["locked_test"] = {
        "copied_to": str(test_path.relative_to(ROOT)).replace("\\", "/"),
        "sha256_before": test_sha_before,
        "sha256_after": sha256(test_path),
        "byte_identical": sha256(test_path) == test_sha_before,
    }
    summary["review_csv_sha256"] = sha256(args.user_review_csv)

    audit = {
        "run_id": args.out_version,
        "status": STATUS,
        "claim_allowed": False,
        "formal_acceptance_allowed": False,
        "locked_test_read": False,
        "reviewer_id": REVIEWER_ID,
        "annotator_ids": [PASS_A_ID, PASS_B_ID, PASS_C_ID],
        "review_row_count": len(review_rows),
        "applied": summary["applied"],
        "unmatched_review_ids": summary["unmatched_review_ids"],
        "quarantine_count": len(summary["quarantine_needs_review_ids"]),
        "label_distribution": summary["label_distribution"],
        "locked_test_sha256": test_sha_before,
        "byte_identical": True,
    }
    (out_root / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (audit_root / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": STATUS,
                "review_row_count": len(review_rows),
                "applied": summary["applied"],
                "quarantine_count": len(summary["quarantine_needs_review_ids"]),
                "locked_test_byte_identical": summary["locked_test"]["byte_identical"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
