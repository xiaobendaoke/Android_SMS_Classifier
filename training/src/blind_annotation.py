"""Shared helpers for dual-human blind annotation packs."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

ALLOWED_LABELS = {
    "TRANSACTION",
    "AD",
    "HARASS",
    "FRAUD",
    "NEEDS_REVIEW",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def write_csv(path: Path, rows: Sequence[dict], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def cohen_kappa(labels_a: Sequence[str], labels_b: Sequence[str]) -> float:
    count = len(labels_a)
    if count == 0:
        return 1.0
    observed = sum(a == b for a, b in zip(labels_a, labels_b)) / count
    dist_a, dist_b = Counter(labels_a), Counter(labels_b)
    expected = sum(
        (dist_a[label] / count) * (dist_b[label] / count) for label in ALLOWED_LABELS
    )
    return (observed - expected) / (1.0 - expected) if expected < 1.0 else 1.0


def review_key(row: Dict[str, str]) -> str:
    # review_group_id can intentionally repeat for every member of a conflict
    # group; row alignment must therefore use unique review_id when present,
    # otherwise the record id.
    return row.get("review_id") or row.get("id", "")


def validate_blind_sheet(
    name: str,
    rows: Sequence[Dict[str, str]],
    *,
    expected_ids: Sequence[str],
    immutable_fields: Sequence[str],
    require_labels_filled: bool,
) -> Tuple[List[str], str]:
    errors: List[str] = []
    if len(rows) != len(expected_ids):
        return [f"{name}: row_count={len(rows)} expected={len(expected_ids)}"], ""
    got_ids = sorted(row.get("id", "") for row in rows)
    if got_ids != sorted(expected_ids):
        errors.append(f"{name}: id membership differs from pack")
    annotator_ids = set()
    for number, row in enumerate(rows, start=2):
        for field in immutable_fields:
            if field not in row:
                errors.append(f"{name}: row {number} missing immutable field {field}")
        if require_labels_filled:
            label = row.get("label", "")
            if label not in ALLOWED_LABELS:
                errors.append(f"{name}: row {number} invalid/missing label {label!r}")
            annotator = row.get("human_annotator_id", "")
            if not annotator:
                errors.append(f"{name}: row {number} missing human_annotator_id")
            else:
                annotator_ids.add(annotator)
    if require_labels_filled and len(annotator_ids) != 1:
        errors.append(f"{name}: expected one annotator id, got {sorted(annotator_ids)}")
    return errors, next(iter(annotator_ids), "")


def dual_human_evidence_complete(manifest: dict) -> bool:
    evidence = manifest.get("dual_human_evidence", {})
    if not evidence:
        return False
    if evidence.get("independence_attestation") is not True:
        return False
    if evidence.get("saw_model_suggestions") is not False:
        return False
    return bool(evidence.get("started_at") and evidence.get("completed_at"))


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
