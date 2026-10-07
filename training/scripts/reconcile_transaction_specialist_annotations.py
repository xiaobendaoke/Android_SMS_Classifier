#!/usr/bin/env python3
"""Validate two blind annotation sheets and prepare local adjudication."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Sequence

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "interim" / "annotation" / "transaction_specialist"
DEFAULT_MANIFEST = (
    ROOT / "data" / "manifests" / "transaction_specialist_holdout.json"
)
ALLOWED_LABELS = {
    "TRANSACTION",
    "AD",
    "HARASS",
    "FRAUD",
    "NEEDS_REVIEW",
}
IMMUTABLE_FIELDS = (
    "id",
    "text",
    "source",
    "template_group",
    "sender_group",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def write_csv(path: Path, rows: Sequence[Dict[str, str]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def cohen_kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> float:
    count = len(labels_a)
    if count == 0:
        return 0.0
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / count
    dist_a = Counter(labels_a)
    dist_b = Counter(labels_b)
    expected = sum(
        (dist_a[label] / count) * (dist_b[label] / count)
        for label in ALLOWED_LABELS
    )
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1.0 - expected)


def validate_sheet(
    *,
    name: str,
    pool: Sequence[Dict[str, str]],
    rows: Sequence[Dict[str, str]],
) -> tuple[List[str], str]:
    errors: List[str] = []
    if len(rows) != len(pool):
        errors.append(f"{name}: row_count={len(rows)} expected={len(pool)}")
        return errors, ""
    ids = [row.get("id", "") for row in rows]
    if len(ids) != len(set(ids)):
        errors.append(f"{name}: duplicate ids detected")
    expected_ids = [row["id"] for row in pool]
    if ids != expected_ids:
        errors.append(f"{name}: ids/order differ from the original blind sheet")

    for index, (original, row) in enumerate(zip(pool, rows), start=2):
        for field in IMMUTABLE_FIELDS:
            if row.get(field, "") != original.get(field, ""):
                errors.append(
                    f"{name}: row {index} immutable field changed: {field}"
                )
        label = row.get("label", "")
        if label not in ALLOWED_LABELS:
            errors.append(f"{name}: row {index} invalid label: {label!r}")
        if not row.get("human_annotator_id", ""):
            errors.append(f"{name}: row {index} missing human_annotator_id")
        if row.get("coverage_subtype", "") or row.get("prior_label", ""):
            errors.append(
                f"{name}: row {index} blind fields must remain empty"
            )

    annotator_ids = {
        row.get("human_annotator_id", "")
        for row in rows
        if row.get("human_annotator_id", "")
    }
    if len(annotator_ids) != 1:
        errors.append(
            f"{name}: expected one stable annotator id, got {sorted(annotator_ids)}"
        )
    return errors, next(iter(annotator_ids), "")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotation-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    pool_path = args.annotation_dir / "transaction_specialist_pool.csv"
    a_path = args.annotation_dir / "transaction_specialist_annotator_A.csv"
    b_path = args.annotation_dir / "transaction_specialist_annotator_B.csv"
    required = (pool_path, a_path, b_path, args.manifest)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print("Missing required files:\n" + "\n".join(missing), file=sys.stderr)
        return 1

    pool = read_csv(pool_path)
    rows_a = read_csv(a_path)
    rows_b = read_csv(b_path)
    errors_a, annotator_a = validate_sheet(name="A", pool=pool, rows=rows_a)
    errors_b, annotator_b = validate_sheet(name="B", pool=pool, rows=rows_b)
    errors = errors_a + errors_b
    if annotator_a and annotator_a == annotator_b:
        errors.append("A/B must use different human_annotator_id values")
    if errors:
        print("ANNOTATION_VALIDATION_FAILED", file=sys.stderr)
        for error in errors[:100]:
            print(f"- {error}", file=sys.stderr)
        if len(errors) > 100:
            print(f"- ... {len(errors) - 100} additional errors", file=sys.stderr)
        return 2

    labels_a = [row["label"] for row in rows_a]
    labels_b = [row["label"] for row in rows_b]
    agreements: List[Dict[str, str]] = []
    conflicts: List[Dict[str, str]] = []
    pair_counts: Counter[str] = Counter()
    for original, row_a, row_b in zip(pool, rows_a, rows_b):
        pair_counts[f"{row_a['label']} -> {row_b['label']}"] += 1
        common = {
            field: original.get(field, "")
            for field in IMMUTABLE_FIELDS
        }
        common.update(
            {
                "coverage_subtype": original.get("coverage_subtype", ""),
                "prior_label": original.get("prior_label", ""),
                "annotator_a_id": annotator_a,
                "annotator_a_label": row_a["label"],
                "annotator_a_notes": row_a.get("notes", ""),
                "annotator_b_id": annotator_b,
                "annotator_b_label": row_b["label"],
                "annotator_b_notes": row_b.get("notes", ""),
            }
        )
        if row_a["label"] == row_b["label"]:
            common["final_label"] = row_a["label"]
            common["resolution"] = "AGREED"
            agreements.append(common)
        else:
            common.update(
                {
                    "adjudicated_label": "",
                    "adjudicator_id": "",
                    "adjudication_notes": "",
                    "resolution": "PENDING_ADJUDICATION",
                }
            )
            conflicts.append(common)

    common_fields = [
        *IMMUTABLE_FIELDS,
        "coverage_subtype",
        "prior_label",
        "annotator_a_id",
        "annotator_a_label",
        "annotator_a_notes",
        "annotator_b_id",
        "annotator_b_label",
        "annotator_b_notes",
    ]
    agreement_path = args.annotation_dir / "transaction_specialist_agreements.csv"
    conflict_path = args.annotation_dir / "transaction_specialist_conflicts.csv"
    write_csv(
        agreement_path,
        agreements,
        [*common_fields, "final_label", "resolution"],
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

    report = {
        "status": (
            "PENDING_ADJUDICATION" if conflicts else "DUAL_ANNOTATION_COMPLETE"
        ),
        "claim_allowed": False,
        "total": len(pool),
        "agreement_count": len(agreements),
        "conflict_count": len(conflicts),
        "raw_agreement": len(agreements) / len(pool) if pool else 0.0,
        "cohen_kappa": cohen_kappa(labels_a, labels_b),
        "annotator_a": {
            "id": annotator_a,
            "label_distribution": dict(Counter(labels_a)),
            "sha256": sha256_file(a_path),
        },
        "annotator_b": {
            "id": annotator_b,
            "label_distribution": dict(Counter(labels_b)),
            "sha256": sha256_file(b_path),
        },
        "disagreement_pairs": {
            pair: count
            for pair, count in sorted(pair_counts.items())
            if pair.split(" -> ", 1)[0] != pair.split(" -> ", 1)[1]
        },
        "agreements_path": str(agreement_path.relative_to(ROOT)).replace("\\", "/"),
        "agreements_sha256": sha256_file(agreement_path),
        "conflicts_path": str(conflict_path.relative_to(ROOT)).replace("\\", "/"),
        "conflicts_sha256": sha256_file(conflict_path),
    }
    report_path = args.annotation_dir / "transaction_specialist_reconciliation.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest["status"] = report["status"]
    manifest["claim_allowed"] = False
    manifest["dual_annotation"] = {
        **report,
        "report_path": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "report_sha256": sha256_file(report_path),
    }
    manifest["claim_note"] = (
        "Dual annotation is complete but conflicts must be independently "
        "adjudicated and the final labels frozen before any metric claim."
        if conflicts
        else "Dual annotation agrees on all rows; final freeze is still required."
    )
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": report["status"],
                "total": report["total"],
                "agreement_count": report["agreement_count"],
                "conflict_count": report["conflict_count"],
                "raw_agreement": report["raw_agreement"],
                "cohen_kappa": report["cohen_kappa"],
                "conflicts_path": report["conflicts_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
