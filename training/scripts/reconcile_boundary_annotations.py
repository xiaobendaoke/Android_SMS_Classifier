#!/usr/bin/env python3
"""Validate boundary A/B sheets and generate a blind conflict adjudication CSV."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Sequence

ROOT = Path(__file__).resolve().parent.parent
ANNOTATION_DIR = ROOT / "data" / "interim" / "annotation" / "boundary_v1"
MANIFEST_PATH = ROOT / "data" / "manifests" / "boundary_annotation_v1.json"
ALLOWED_LABELS = {
    "TRANSACTION",
    "AD",
    "HARASS",
    "FRAUD",
    "NEEDS_REVIEW",
}
IMMUTABLE_FIELDS = ("id", "text", "source", "template_group", "sender_group")
BLIND_FIELDS = {
    "boundary_bucket",
    "prior_label",
    "teacher_prediction",
    "teacher_transaction_score",
    "teacher_harass_score",
    "student_prediction",
    "student_transaction_score",
    "student_harass_score",
}


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def write_csv(path: Path, rows: Sequence[dict], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(
    name: str,
    pool: Sequence[Dict[str, str]],
    rows: Sequence[Dict[str, str]],
) -> tuple[List[str], str]:
    errors: List[str] = []
    if len(rows) != len(pool):
        return [f"{name}: row_count={len(rows)} expected={len(pool)}"], ""
    if [row["id"] for row in rows] != [row["id"] for row in pool]:
        errors.append(f"{name}: ids/order differ from the blind source")
    for number, (source, row) in enumerate(zip(pool, rows), start=2):
        for field in IMMUTABLE_FIELDS:
            if row.get(field, "") != source.get(field, ""):
                errors.append(f"{name}: row {number} changed {field}")
        if row.get("label", "") not in ALLOWED_LABELS:
            errors.append(
                f"{name}: row {number} invalid label {row.get('label', '')!r}"
            )
        if not row.get("human_annotator_id", ""):
            errors.append(f"{name}: row {number} missing annotator id")
        if any(row.get(field, "") for field in BLIND_FIELDS):
            errors.append(f"{name}: row {number} modified blind fields")
    ids = {
        row["human_annotator_id"]
        for row in rows
        if row.get("human_annotator_id", "")
    }
    if len(ids) != 1:
        errors.append(f"{name}: expected one annotator id, got {sorted(ids)}")
    return errors, next(iter(ids), "")


def kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> float:
    count = len(labels_a)
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / max(count, 1)
    dist_a, dist_b = Counter(labels_a), Counter(labels_b)
    expected = sum(
        (dist_a[label] / count) * (dist_b[label] / count)
        for label in ALLOWED_LABELS
    )
    return (observed - expected) / (1.0 - expected) if expected < 1.0 else 1.0


def main() -> int:
    pool_path = ANNOTATION_DIR / "boundary_pool.csv"
    a_path = ANNOTATION_DIR / "boundary_annotator_A.csv"
    b_path = ANNOTATION_DIR / "boundary_annotator_B.csv"
    pool, rows_a, rows_b = map(read_csv, (pool_path, a_path, b_path))
    errors_a, annotator_a = validate("A", pool, rows_a)
    errors_b, annotator_b = validate("B", pool, rows_b)
    errors = errors_a + errors_b
    if annotator_a and annotator_a == annotator_b:
        errors.append("A and B annotator ids must differ")
    if errors:
        print("BOUNDARY_ANNOTATION_VALIDATION_FAILED", file=sys.stderr)
        for error in errors[:100]:
            print(f"- {error}", file=sys.stderr)
        return 2

    agreements, conflicts = [], []
    pair_counts: Counter[str] = Counter()
    for source, row_a, row_b in zip(pool, rows_a, rows_b):
        pair_counts[f"{row_a['label']} -> {row_b['label']}"] += 1
        if row_a["label"] == row_b["label"]:
            agreements.append(
                {
                    "id": source["id"],
                    "text": source["text"],
                    "prior_label": source["prior_label"],
                    "boundary_bucket": source["boundary_bucket"],
                    "annotator_a_id": annotator_a,
                    "annotator_a_label": row_a["label"],
                    "annotator_b_id": annotator_b,
                    "annotator_b_label": row_b["label"],
                    "final_label": row_a["label"],
                    "resolution": "AGREED",
                }
            )
        else:
            conflicts.append(
                {
                    "id": source["id"],
                    "text": source["text"],
                    "annotator_a_id": annotator_a,
                    "annotator_a_label": row_a["label"],
                    "annotator_a_notes": row_a.get("notes", ""),
                    "annotator_b_id": annotator_b,
                    "annotator_b_label": row_b["label"],
                    "annotator_b_notes": row_b.get("notes", ""),
                    "adjudicated_label": "",
                    "adjudicator_id": "",
                    "adjudication_notes": "",
                    "resolution": "PENDING_ADJUDICATION",
                }
            )
    agreement_path = ANNOTATION_DIR / "boundary_agreements.csv"
    conflict_path = ANNOTATION_DIR / "boundary_conflicts.csv"
    write_csv(
        agreement_path,
        agreements,
        [
            "id",
            "text",
            "prior_label",
            "boundary_bucket",
            "annotator_a_id",
            "annotator_a_label",
            "annotator_b_id",
            "annotator_b_label",
            "final_label",
            "resolution",
        ],
    )
    write_csv(
        conflict_path,
        conflicts,
        [
            "id",
            "text",
            "annotator_a_id",
            "annotator_a_label",
            "annotator_a_notes",
            "annotator_b_id",
            "annotator_b_label",
            "annotator_b_notes",
            "adjudicated_label",
            "adjudicator_id",
            "adjudication_notes",
            "resolution",
        ],
    )
    blank_conflicts_sha = sha256_file(conflict_path)
    report = {
        "status": (
            "PENDING_ADJUDICATION" if conflicts else "DUAL_ANNOTATION_COMPLETE"
        ),
        "total": len(pool),
        "agreement_count": len(agreements),
        "conflict_count": len(conflicts),
        "raw_agreement": len(agreements) / len(pool),
        "cohen_kappa": kappa(
            [row["label"] for row in rows_a],
            [row["label"] for row in rows_b],
        ),
        "annotator_a": {"id": annotator_a, "sha256": sha256_file(a_path)},
        "annotator_b": {"id": annotator_b, "sha256": sha256_file(b_path)},
        "disagreement_pairs": {
            pair: count
            for pair, count in sorted(pair_counts.items())
            if pair.split(" -> ")[0] != pair.split(" -> ")[1]
        },
        "agreements_path": str(agreement_path.relative_to(ROOT)).replace("\\", "/"),
        "agreements_sha256": sha256_file(agreement_path),
        "conflicts_path": str(conflict_path.relative_to(ROOT)).replace("\\", "/"),
        "conflicts_sha256": blank_conflicts_sha,
        "blank_conflicts_sha256": blank_conflicts_sha,
        "completed_conflicts_sha256": None,
        "claim_allowed": False,
    }
    report_path = ANNOTATION_DIR / "boundary_reconciliation.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    # Reconciliation alone never proves dual-human gold; keep provisional unless
    # a later finalization step records independence evidence.
    manifest["status"] = report["status"]
    manifest["claim_allowed"] = False
    manifest["dual_human_evidence_complete"] = False
    manifest["dual_annotation"] = {
        **report,
        "report_path": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "report_sha256": sha256_file(report_path),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "total",
                    "agreement_count",
                    "conflict_count",
                    "raw_agreement",
                    "cohen_kappa",
                    "conflicts_path",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
