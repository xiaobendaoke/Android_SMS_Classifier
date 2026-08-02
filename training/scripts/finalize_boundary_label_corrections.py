#!/usr/bin/env python3
"""Finalize adjudicated TRAIN-only boundary labels as a correction overlay.

Without auditable dual-human independence evidence, status remains
PROVISIONAL_AUTOMATED_REVIEW and claim_allowed=false.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
ANNOTATION_DIR = ROOT / "data" / "interim" / "annotation" / "boundary_v1"
MANIFEST_PATH = ROOT / "data" / "manifests" / "boundary_annotation_v1.json"
CORRECTIONS_PATH = (
    ROOT / "data" / "manifests" / "boundary_label_corrections_v1.json"
)
GUIDE_PATH = ROOT.parent / "docs" / "labeling-guide.md"
ALLOWED_LABELS = {
    "TRANSACTION",
    "AD",
    "HARASS",
    "FRAUD",
    "NEEDS_REVIEW",
}


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dual_human_evidence_complete(manifest: dict) -> bool:
    evidence = manifest.get("dual_human_evidence", {})
    required = [
        "independence_attestation",
        "started_at",
        "completed_at",
        "annotator_roster_internal_ref",
        "saw_model_suggestions",
    ]
    if not evidence:
        return False
    if evidence.get("independence_attestation") is not True:
        return False
    if evidence.get("saw_model_suggestions") is not False:
        return False
    return all(evidence.get(key) for key in required[:-1])


def main() -> int:
    pool_path = ANNOTATION_DIR / "boundary_pool.csv"
    a_path = ANNOTATION_DIR / "boundary_annotator_A.csv"
    b_path = ANNOTATION_DIR / "boundary_annotator_B.csv"
    agreements_path = ANNOTATION_DIR / "boundary_agreements.csv"
    conflicts_path = ANNOTATION_DIR / "boundary_conflicts.csv"
    paths = (pool_path, a_path, b_path, agreements_path, conflicts_path)
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        print("Missing files:\n" + "\n".join(missing), file=sys.stderr)
        return 1

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    dual = manifest.get("dual_annotation", {})
    if sha256_file(a_path) != dual.get("annotator_a", {}).get("sha256"):
        print("Annotator A sheet changed after reconciliation.", file=sys.stderr)
        return 2
    if sha256_file(b_path) != dual.get("annotator_b", {}).get("sha256"):
        print("Annotator B sheet changed after reconciliation.", file=sys.stderr)
        return 2

    pool = read_csv(pool_path)
    rows_a = read_csv(a_path)
    rows_b = read_csv(b_path)
    agreements = read_csv(agreements_path)
    conflicts = read_csv(conflicts_path)
    pool_by_id = {row["id"]: row for row in pool}
    a_by_id = {row["id"]: row for row in rows_a}
    b_by_id = {row["id"]: row for row in rows_b}
    agreement_by_id = {row["id"]: row for row in agreements}
    conflict_by_id = {row["id"]: row for row in conflicts}
    expected_conflicts = [
        row["id"]
        for row, row_a, row_b in zip(pool, rows_a, rows_b)
        if row_a["label"] != row_b["label"]
    ]
    errors: List[str] = []
    if [row.get("id", "") for row in conflicts] != expected_conflicts:
        errors.append("Conflict ids/order differ from A/B disagreements")
    if len(conflicts) != int(dual.get("conflict_count", len(conflicts))):
        errors.append("Conflict count differs from reconciliation report")

    adjudicator_ids = set()
    for number, row in enumerate(conflicts, start=2):
        record_id = row.get("id", "")
        source = pool_by_id.get(record_id)
        if source is None:
            errors.append(f"row {number}: unknown id")
            continue
        if row.get("text", "") != source["text"]:
            errors.append(f"row {number}: text changed")
        if row.get("annotator_a_label", "") != a_by_id[record_id]["label"]:
            errors.append(f"row {number}: A label changed")
        if row.get("annotator_b_label", "") != b_by_id[record_id]["label"]:
            errors.append(f"row {number}: B label changed")
        final_label = row.get("adjudicated_label", "")
        if final_label not in ALLOWED_LABELS:
            errors.append(f"row {number}: invalid adjudicated label")
        adjudicator_id = row.get("adjudicator_id", "")
        if not adjudicator_id:
            errors.append(f"row {number}: missing adjudicator id")
        else:
            adjudicator_ids.add(adjudicator_id)
        if (
            final_label
            and final_label
            not in {
                a_by_id[record_id]["label"],
                b_by_id[record_id]["label"],
            }
            and not row.get("adjudication_notes", "")
        ):
            errors.append(f"row {number}: third-label choice requires notes")
    if conflicts and len(adjudicator_ids) != 1:
        errors.append(f"Expected one adjudicator id, got {sorted(adjudicator_ids)}")
    annotator_a = dual.get("annotator_a", {}).get("id", "")
    annotator_b = dual.get("annotator_b", {}).get("id", "")
    adjudicator_id = next(iter(adjudicator_ids), "")
    if adjudicator_id in {annotator_a, annotator_b}:
        errors.append("Adjudicator must differ from A and B")
    if errors:
        print("BOUNDARY_ADJUDICATION_VALIDATION_FAILED", file=sys.stderr)
        for error in errors[:100]:
            print(f"- {error}", file=sys.stderr)
        return 3

    corrections = []
    for source in pool:
        record_id = source["id"]
        if record_id in agreement_by_id:
            final_label = agreement_by_id[record_id]["final_label"]
            resolution = "AGREED"
            human_ids = [annotator_a, annotator_b]
        else:
            conflict = conflict_by_id[record_id]
            final_label = conflict["adjudicated_label"]
            resolution = "ADJUDICATED"
            human_ids = [annotator_a, annotator_b, conflict["adjudicator_id"]]
        corrections.append(
            {
                "id": record_id,
                "text_sha256": hashlib.sha256(
                    source["text"].encode("utf-8")
                ).hexdigest(),
                "prior_label": source["prior_label"],
                "final_label": final_label,
                "boundary_bucket": source["boundary_bucket"],
                "resolution": resolution,
                "human_annotator_ids": human_ids,
            }
        )
    changed = [
        row for row in corrections if row["prior_label"] != row["final_label"]
    ]
    evidence_ok = dual_human_evidence_complete(manifest)
    status = (
        "FROZEN_DUAL_HUMAN_ANNOTATED"
        if evidence_ok
        else "PROVISIONAL_AUTOMATED_REVIEW"
    )
    claim_allowed = bool(evidence_ok)
    if status == "FROZEN_DUAL_HUMAN_ANNOTATED" and not claim_allowed:
        status = "PROVISIONAL_AUTOMATED_REVIEW"

    completed_conflicts_sha = sha256_file(conflicts_path)
    guide_sha = sha256_file(GUIDE_PATH) if GUIDE_PATH.exists() else None
    payload = {
        "version": "1.0.0",
        "status": status,
        "claim_allowed": claim_allowed,
        "dual_human_evidence_complete": evidence_ok,
        "source_split": "train",
        "locked_validation_or_test_read": False,
        "count": len(corrections),
        "changed_label_count": len(changed),
        "removed_needs_review_count": sum(
            row["final_label"] == "NEEDS_REVIEW" for row in corrections
        ),
        "final_label_distribution": dict(
            Counter(row["final_label"] for row in corrections)
        ),
        "changed_by_transition": dict(
            Counter(
                f"{row['prior_label']} -> {row['final_label']}"
                for row in changed
            )
        ),
        "annotator_ids": [annotator_a, annotator_b],
        "adjudicator_id": adjudicator_id or None,
        "annotation_guide_sha256": guide_sha,
        "annotator_a_sha256": sha256_file(a_path),
        "annotator_b_sha256": sha256_file(b_path),
        "completed_conflicts_sha256": completed_conflicts_sha,
        "blank_conflicts_sha256": dual.get("blank_conflicts_sha256"),
        "corrections": corrections,
    }
    CORRECTIONS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest["status"] = status
    manifest["claim_allowed"] = claim_allowed
    manifest["dual_human_evidence_complete"] = evidence_ok
    manifest["annotation_guide_sha256"] = guide_sha
    dual_status = status if evidence_ok else "PROVISIONAL_AUTOMATED_REVIEW"
    manifest["dual_annotation"] = {
        **dual,
        "status": dual_status,
        "completed_conflicts_sha256": completed_conflicts_sha,
        "annotator_a": {
            "id": annotator_a,
            "sha256": sha256_file(a_path),
        },
        "annotator_b": {
            "id": annotator_b,
            "sha256": sha256_file(b_path),
        },
        "adjudicator_id": adjudicator_id or None,
    }
    manifest["corrections"] = {
        "path": str(CORRECTIONS_PATH.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256_file(CORRECTIONS_PATH),
        "count": len(corrections),
        "changed_label_count": len(changed),
        "removed_needs_review_count": payload["removed_needs_review_count"],
        "status": status,
        "claim_allowed": claim_allowed,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "claim_allowed": claim_allowed,
                "dual_human_evidence_complete": evidence_ok,
                "count": payload["count"],
                "changed_label_count": payload["changed_label_count"],
                "removed_needs_review_count": payload[
                    "removed_needs_review_count"
                ],
                "completed_conflicts_sha256": completed_conflicts_sha,
                "corrections_path": str(
                    CORRECTIONS_PATH.relative_to(ROOT)
                ).replace("\\", "/"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
