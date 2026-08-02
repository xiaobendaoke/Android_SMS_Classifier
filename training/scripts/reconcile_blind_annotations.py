#!/usr/bin/env python3
"""Reconcile filled A/B blind sheets into agreements/conflicts."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.blind_annotation import (  # noqa: E402
    ALLOWED_LABELS,
    cohen_kappa,
    load_manifest,
    read_csv,
    review_key,
    sha256_file,
    validate_blind_sheet,
    write_csv,
)

GUIDE_PATH = ROOT.parent / "docs" / "labeling-guide.md"


def relpath(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reconcile blind A/B annotation packs.")
    parser.add_argument("--pack-dir", type=Path, required=True)
    parser.add_argument("--manifest-name", default="manifest.json")
    parser.add_argument("--sheet-a", default="")
    parser.add_argument("--sheet-b", default="")
    parser.add_argument("--id-field", default="id")
    return parser


def resolve_sheet(pack_dir: Path, manifest: dict, side: str, override: str) -> Path:
    if override:
        return (pack_dir / override).resolve()
    files = manifest.get("files", {})
    key = "annotator_a" if side == "A" else "annotator_b"
    alt = "blind_annotator_A" if side == "A" else "blind_annotator_B"
    rel = (
        files.get(key, {}).get("path")
        or files.get(alt, {}).get("path")
        or ""
    )
    if not rel:
        raise SystemExit(f"Manifest missing {side} sheet path")
    path = Path(rel)
    if path.is_absolute() and path.exists():
        return path
    # Paths in manifest are usually repo-relative under training/
    candidate = ROOT / rel
    if candidate.exists():
        return candidate
    return pack_dir / path.name


def resolve_pool(pack_dir: Path, manifest: dict) -> Path:
    files = manifest.get("files", {})
    rel = (
        files.get("internal_pool", {}).get("path")
        or files.get("conflict_pool", {}).get("path")
        or ""
    )
    if not rel:
        raise SystemExit("Manifest missing immutable internal/conflict pool path")
    path = Path(rel)
    if path.is_absolute() and path.exists():
        return path
    candidate = ROOT / rel
    if candidate.exists():
        return candidate
    return pack_dir / path.name


def validate_against_pool(
    name: str,
    rows: List[dict],
    pool_by_key: dict[str, dict],
    *,
    allowed_fields: set[str],
) -> List[str]:
    """Require sheet membership and immutable review/id/text values from pool."""
    errors: List[str] = []
    seen_keys = set()
    for number, row in enumerate(rows, start=2):
        extra = set(row) - allowed_fields
        if extra:
            errors.append(
                f"{name}: row {number} contains forbidden columns {sorted(extra)}"
            )
        key = review_key(row)
        source = pool_by_key.get(key)
        if not source:
            errors.append(f"{name}: row {number} unknown review key {key!r}")
            continue
        if key in seen_keys:
            errors.append(f"{name}: row {number} duplicate review key {key!r}")
        seen_keys.add(key)
        for field in ("id", "text"):
            if row.get(field, "") != source.get(field, ""):
                errors.append(f"{name}: row {number} changed immutable {field}")
        source_group = source.get("review_id") or source.get("review_group_id")
        row_group = row.get("review_id") or row.get("review_group_id")
        if row_group != source_group:
            errors.append(f"{name}: row {number} changed immutable review key")
    if seen_keys != set(pool_by_key):
        errors.append(f"{name}: review membership differs from immutable pool")
    return errors


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    pack_dir = args.pack_dir.resolve()
    manifest_path = pack_dir / args.manifest_name
    if not manifest_path.exists():
        print(f"Missing manifest: {manifest_path}", file=sys.stderr)
        return 1
    manifest = load_manifest(manifest_path)
    if manifest.get("status") not in {
        "PENDING_DUAL_HUMAN_ANNOTATION",
        "READY_FOR_HUMAN_ANNOTATION",
        "PENDING_ADJUDICATION",
    }:
        # Allow re-run from ready/pending states only.
        pass

    a_path = resolve_sheet(pack_dir, manifest, "A", args.sheet_a)
    b_path = resolve_sheet(pack_dir, manifest, "B", args.sheet_b)
    pool_path = resolve_pool(pack_dir, manifest)
    rows_a = read_csv(a_path)
    rows_b = read_csv(b_path)
    pool_rows = read_csv(pool_path)
    pool_by_key = {review_key(row): row for row in pool_rows}
    if len(pool_by_key) != len(pool_rows):
        print("Immutable pool contains duplicate review keys.", file=sys.stderr)
        return 1

    expected_sha_a = (
        manifest.get("files", {}).get("annotator_a", {}).get("sha256")
        or manifest.get("files", {}).get("blind_annotator_A", {}).get("sha256")
    )
    expected_sha_b = (
        manifest.get("files", {}).get("annotator_b", {}).get("sha256")
        or manifest.get("files", {}).get("blind_annotator_B", {}).get("sha256")
    )
    # After humans fill labels, sheet SHA changes. Bind immutable fields to the
    # original internal pool instead of trusting the two edited sheets.
    expected_ids = [row.get("id", "") for row in pool_rows]
    immutable = ["id", "text"]
    if rows_a and "review_id" in rows_a[0]:
        immutable = ["review_id", "id", "text"]
    elif rows_a and "review_group_id" in rows_a[0]:
        immutable = ["review_group_id", "id", "text"]

    errors_a, annotator_a = validate_blind_sheet(
        "A",
        rows_a,
        expected_ids=expected_ids,
        immutable_fields=immutable,
        require_labels_filled=True,
    )
    errors_b, annotator_b = validate_blind_sheet(
        "B",
        rows_b,
        expected_ids=expected_ids,
        immutable_fields=immutable,
        require_labels_filled=True,
    )
    errors = errors_a + errors_b
    allowed_fields = {
        "id",
        "text",
        "label",
        "notes",
        "human_annotator_id",
        "review_id",
        "review_group_id",
    }
    errors.extend(
        validate_against_pool("A", rows_a, pool_by_key, allowed_fields=allowed_fields)
    )
    errors.extend(
        validate_against_pool("B", rows_b, pool_by_key, allowed_fields=allowed_fields)
    )
    if annotator_a and annotator_a == annotator_b:
        errors.append("A and B annotator ids must differ")
    if not annotator_a or not annotator_b:
        errors.append("Both annotator ids are required")

    # Align by review key then id.
    by_a = {review_key(row): row for row in rows_a}
    by_b = {review_key(row): row for row in rows_b}
    if set(by_a) != set(by_b):
        errors.append("A/B review keys differ")
    if errors:
        print("BLIND_ANNOTATION_VALIDATION_FAILED", file=sys.stderr)
        for error in errors[:100]:
            print(f"- {error}", file=sys.stderr)
        return 2

    agreements, conflicts = [], []
    pair_counts: Counter[str] = Counter()
    for key in sorted(by_a):
        row_a = by_a[key]
        row_b = by_b[key]
        if row_a.get("text") != row_b.get("text") or row_a.get("id") != row_b.get("id"):
            print(f"Immutable mismatch for {key}", file=sys.stderr)
            return 2
        pair_counts[f"{row_a['label']} -> {row_b['label']}"] += 1
        base = {
            "review_id": key,
            "id": row_a["id"],
            "text": row_a["text"],
            "annotator_a_id": annotator_a,
            "annotator_a_label": row_a["label"],
            "annotator_a_notes": row_a.get("notes", ""),
            "annotator_b_id": annotator_b,
            "annotator_b_label": row_b["label"],
            "annotator_b_notes": row_b.get("notes", ""),
        }
        if row_a["label"] == row_b["label"]:
            agreements.append(
                {
                    **base,
                    "final_label": row_a["label"],
                    "resolution": "AGREED",
                }
            )
        else:
            conflicts.append(
                {
                    **base,
                    "adjudicated_label": "",
                    "adjudicator_id": "",
                    "adjudication_notes": "",
                    "resolution": "PENDING_ADJUDICATION",
                }
            )

    agreement_path = pack_dir / "agreements.csv"
    conflict_path = pack_dir / "conflicts.csv"
    fields_agree = [
        "review_id",
        "id",
        "text",
        "annotator_a_id",
        "annotator_a_label",
        "annotator_a_notes",
        "annotator_b_id",
        "annotator_b_label",
        "annotator_b_notes",
        "final_label",
        "resolution",
    ]
    fields_conflict = [
        "review_id",
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
    ]
    write_csv(agreement_path, agreements, fields_agree)
    write_csv(conflict_path, conflicts, fields_conflict)
    blank_conflicts_sha = sha256_file(conflict_path)

    report = {
        "status": "PENDING_ADJUDICATION" if conflicts else "DUAL_ANNOTATION_COMPLETE",
        "total": len(by_a),
        "agreement_count": len(agreements),
        "conflict_count": len(conflicts),
        "raw_agreement": len(agreements) / max(len(by_a), 1),
        "cohen_kappa": cohen_kappa(
            [by_a[k]["label"] for k in sorted(by_a)],
            [by_b[k]["label"] for k in sorted(by_a)],
        ),
        "annotator_a": {"id": annotator_a, "sha256": sha256_file(a_path)},
        "annotator_b": {"id": annotator_b, "sha256": sha256_file(b_path)},
        "blank_conflicts_sha256": blank_conflicts_sha,
        "completed_conflicts_sha256": None,
        "conflicts_sha256": blank_conflicts_sha,
        "claim_allowed": False,
        "annotation_guide_sha256": (
            sha256_file(GUIDE_PATH) if GUIDE_PATH.exists() else None
        ),
        "disagreement_pairs": {
            pair: count
            for pair, count in sorted(pair_counts.items())
            if pair.split(" -> ")[0] != pair.split(" -> ")[1]
        },
    }
    report_path = pack_dir / "reconciliation.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest["status"] = report["status"]
    manifest["claim_allowed"] = False
    manifest["dual_human_evidence_complete"] = False
    manifest["dual_annotation"] = {
        **report,
        "report_path": relpath(report_path),
        "report_sha256": sha256_file(report_path),
        "agreements_path": relpath(agreement_path),
        "conflicts_path": relpath(conflict_path),
    }
    # Preserve original blank sheet SHAs under separate keys.
    if expected_sha_a:
        manifest.setdefault("blank_sheet_sha256", {})["A"] = expected_sha_a
    if expected_sha_b:
        manifest.setdefault("blank_sheet_sha256", {})["B"] = expected_sha_b
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "total": report["total"],
                "agreement_count": report["agreement_count"],
                "conflict_count": report["conflict_count"],
                "cohen_kappa": report["cohen_kappa"],
                "claim_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
