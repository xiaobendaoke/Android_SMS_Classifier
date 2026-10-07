#!/usr/bin/env python3
"""Validate adjudication and freeze the dual-human transaction specialist set."""
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
DEFAULT_RAW_DIR = ROOT / "data" / "raw"
ALLOWED_LABELS = {
    "TRANSACTION",
    "AD",
    "HARASS",
    "FRAUD",
    "NEEDS_REVIEW",
}


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


def write_csv(path: Path, rows: Sequence[Dict[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def load_raw_records(raw_dir: Path) -> Dict[str, List[dict]]:
    records: Dict[str, List[dict]] = {}
    for path in sorted(raw_dir.rglob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: {exc}") from exc
                record_id = str(row.get("id", ""))
                if record_id:
                    records.setdefault(record_id, []).append(row)
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotation-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    pool_path = args.annotation_dir / "transaction_specialist_pool.csv"
    a_path = args.annotation_dir / "transaction_specialist_annotator_A.csv"
    b_path = args.annotation_dir / "transaction_specialist_annotator_B.csv"
    agreements_path = args.annotation_dir / "transaction_specialist_agreements.csv"
    conflicts_path = args.annotation_dir / "transaction_specialist_conflicts.csv"
    required = (
        pool_path,
        a_path,
        b_path,
        agreements_path,
        conflicts_path,
        args.manifest,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print("Missing required files:\n" + "\n".join(missing), file=sys.stderr)
        return 1

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    dual = manifest.get("dual_annotation", {})
    expected_a_sha = dual.get("annotator_a", {}).get("sha256")
    expected_b_sha = dual.get("annotator_b", {}).get("sha256")
    if expected_a_sha and sha256_file(a_path) != expected_a_sha:
        print("Annotator A sheet changed after reconciliation.", file=sys.stderr)
        return 2
    if expected_b_sha and sha256_file(b_path) != expected_b_sha:
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

    errors: List[str] = []
    expected_conflict_ids = [
        row["id"]
        for row_a, row_b, row in zip(rows_a, rows_b, pool)
        if row_a["label"] != row_b["label"]
    ]
    if [row.get("id", "") for row in conflicts] != expected_conflict_ids:
        errors.append("Conflict ids/order differ from the reconciled A/B disagreements")
    if len(conflicts) != int(dual.get("conflict_count", len(conflicts))):
        errors.append("Conflict count differs from reconciliation report")

    adjudicator_ids = set()
    for csv_row, conflict in enumerate(conflicts, start=2):
        record_id = conflict.get("id", "")
        original = pool_by_id.get(record_id)
        if original is None:
            errors.append(f"row {csv_row}: unknown id {record_id!r}")
            continue
        if conflict.get("text", "") != original.get("text", ""):
            errors.append(f"row {csv_row}: text changed")
        row_a = a_by_id[record_id]
        row_b = b_by_id[record_id]
        if conflict.get("annotator_a_label", "") != row_a["label"]:
            errors.append(f"row {csv_row}: annotator A label changed")
        if conflict.get("annotator_b_label", "") != row_b["label"]:
            errors.append(f"row {csv_row}: annotator B label changed")
        label = conflict.get("adjudicated_label", "")
        if label not in ALLOWED_LABELS:
            errors.append(f"row {csv_row}: invalid adjudicated_label {label!r}")
        adjudicator_id = conflict.get("adjudicator_id", "")
        if not adjudicator_id:
            errors.append(f"row {csv_row}: missing adjudicator_id")
        else:
            adjudicator_ids.add(adjudicator_id)
        if (
            label
            and label not in {row_a["label"], row_b["label"]}
            and not conflict.get("adjudication_notes", "")
        ):
            errors.append(
                f"row {csv_row}: note required when choosing a third label"
            )

    if len(adjudicator_ids) != 1:
        errors.append(
            f"Expected one stable adjudicator id, got {sorted(adjudicator_ids)}"
        )
    annotator_a = dual.get("annotator_a", {}).get("id", "")
    annotator_b = dual.get("annotator_b", {}).get("id", "")
    adjudicator_id = next(iter(adjudicator_ids), "")
    if adjudicator_id in {annotator_a, annotator_b}:
        errors.append("Adjudicator id must differ from annotator A and B")
    if errors:
        print("ADJUDICATION_VALIDATION_FAILED", file=sys.stderr)
        for error in errors[:100]:
            print(f"- {error}", file=sys.stderr)
        return 3

    raw_records = load_raw_records(args.raw_dir)
    frozen_rows: List[Dict[str, object]] = []
    jsonl_rows: List[dict] = []
    missing_raw: List[str] = []
    raw_text_mismatch_ids: List[str] = []
    for original in pool:
        record_id = original["id"]
        row_a = a_by_id[record_id]
        row_b = b_by_id[record_id]
        if record_id in agreement_by_id:
            final_label = agreement_by_id[record_id]["final_label"]
            resolution = "AGREED"
            final_adjudicator_id = ""
            adjudication_notes = ""
            human_ids = [annotator_a, annotator_b]
        else:
            conflict = conflict_by_id[record_id]
            final_label = conflict["adjudicated_label"]
            resolution = "ADJUDICATED"
            final_adjudicator_id = conflict["adjudicator_id"]
            adjudication_notes = conflict.get("adjudication_notes", "")
            human_ids = [annotator_a, annotator_b, final_adjudicator_id]

        id_candidates = raw_records.get(record_id, [])
        candidates = [
            row
            for row in id_candidates
            if str(row.get("text", "")) == original["text"]
        ]
        if not candidates:
            source_candidates = [
                row
                for row in id_candidates
                if str(row.get("source", "")) == original["source"]
            ]
            candidates = source_candidates or id_candidates
            if candidates:
                raw_text_mismatch_ids.append(record_id)
            else:
                missing_raw.append(record_id)
                continue
        raw = dict(candidates[0])
        raw.update(
            {
                "id": record_id,
                "text": original["text"],
                "label": final_label,
                "language": "zh",
                "source": original["source"],
                "sender_group": original["sender_group"],
                "template_group": original["template_group"],
                "split": "test",
                "annotator_ids": human_ids,
                "specialist_holdout": True,
                "annotation_resolution": resolution,
            }
        )
        jsonl_rows.append(raw)
        frozen_rows.append(
            {
                "id": record_id,
                "text": original["text"],
                "final_label": final_label,
                "coverage_subtype": original.get("coverage_subtype", ""),
                "source": original["source"],
                "template_group": original["template_group"],
                "sender_group": original["sender_group"],
                "resolution": resolution,
                "annotator_a_id": annotator_a,
                "annotator_b_id": annotator_b,
                "adjudicator_id": final_adjudicator_id,
                "adjudication_notes": adjudication_notes,
            }
        )
    if missing_raw:
        print(
            f"Cannot reconstruct {len(missing_raw)} rows from raw data; "
            f"first ids: {missing_raw[:10]}",
            file=sys.stderr,
        )
        return 4

    freeze_csv = args.annotation_dir / "transaction_specialist_frozen.csv"
    freeze_jsonl = args.annotation_dir / "transaction_specialist_frozen.jsonl"
    write_csv(
        freeze_csv,
        frozen_rows,
        [
            "id",
            "text",
            "final_label",
            "coverage_subtype",
            "source",
            "template_group",
            "sender_group",
            "resolution",
            "annotator_a_id",
            "annotator_b_id",
            "adjudicator_id",
            "adjudication_notes",
        ],
    )
    with freeze_jsonl.open("w", encoding="utf-8") as handle:
        for row in jsonl_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    final_distribution = Counter(
        str(row["final_label"]) for row in frozen_rows
    )
    changed_from_prior = sum(
        row["final_label"] != "TRANSACTION" for row in frozen_rows
    )
    freeze_report = {
        "status": "FROZEN_DUAL_HUMAN_ANNOTATED",
        "claim_allowed": False,
        "count": len(frozen_rows),
        "agreement_count": len(agreements),
        "adjudicated_count": len(conflicts),
        "annotator_ids": [annotator_a, annotator_b],
        "adjudicator_id": adjudicator_id,
        "final_label_distribution": dict(final_distribution),
        "changed_from_prior_transaction": changed_from_prior,
        "raw_text_mismatch_count": len(raw_text_mismatch_ids),
        "raw_text_mismatch_ids": raw_text_mismatch_ids,
        "csv_path": str(freeze_csv.relative_to(ROOT)).replace("\\", "/"),
        "csv_sha256": sha256_file(freeze_csv),
        "jsonl_path": str(freeze_jsonl.relative_to(ROOT)).replace("\\", "/"),
        "jsonl_sha256": sha256_file(freeze_jsonl),
    }
    report_path = args.annotation_dir / "transaction_specialist_freeze_report.json"
    report_path.write_text(
        json.dumps(freeze_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    freeze_report["report_path"] = str(report_path.relative_to(ROOT)).replace(
        "\\", "/"
    )
    freeze_report["report_sha256"] = sha256_file(report_path)

    manifest["status"] = "FROZEN_DUAL_HUMAN_ANNOTATED"
    manifest["claim_allowed"] = False
    manifest["freeze"] = freeze_report
    manifest["claim_note"] = (
        "The dual-human specialist set is frozen. A model must be evaluated "
        "against the recorded JSONL SHA before a transaction-recall claim."
    )
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(freeze_report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
