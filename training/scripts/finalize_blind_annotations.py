#!/usr/bin/env python3
"""Finalize adjudicated blind packs. Refuses FROZEN without dual-human evidence."""
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
    dual_human_evidence_complete,
    load_manifest,
    read_csv,
    sha256_file,
)

GUIDE_PATH = ROOT.parent / "docs" / "labeling-guide.md"


def relpath(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finalize adjudicated blind packs.")
    parser.add_argument("--pack-dir", type=Path, required=True)
    parser.add_argument("--manifest-name", default="manifest.json")
    parser.add_argument(
        "--allow-provisional",
        action="store_true",
        help="Emit PROVISIONAL overlay when dual-human evidence is incomplete.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    pack_dir = args.pack_dir.resolve()
    manifest_path = pack_dir / args.manifest_name
    conflicts_path = pack_dir / "conflicts.csv"
    agreements_path = pack_dir / "agreements.csv"
    if not manifest_path.exists() or not conflicts_path.exists() or not agreements_path.exists():
        print("Missing manifest/agreements/conflicts.", file=sys.stderr)
        return 1

    manifest = load_manifest(manifest_path)
    dual = manifest.get("dual_annotation", {})
    agreements = read_csv(agreements_path)
    conflicts = read_csv(conflicts_path)

    errors: List[str] = []
    if len(conflicts) != int(dual.get("conflict_count", len(conflicts))):
        errors.append("Conflict count differs from reconciliation report")

    annotator_a = dual.get("annotator_a", {}).get("id", "")
    annotator_b = dual.get("annotator_b", {}).get("id", "")
    adjudicator_ids = set()
    for number, row in enumerate(conflicts, start=2):
        final_label = row.get("adjudicated_label", "")
        if final_label not in ALLOWED_LABELS:
            errors.append(f"row {number}: invalid/missing adjudicated_label")
        adjudicator = row.get("adjudicator_id", "")
        if not adjudicator:
            errors.append(f"row {number}: missing adjudicator_id")
        else:
            adjudicator_ids.add(adjudicator)
        a_label = row.get("annotator_a_label", "")
        b_label = row.get("annotator_b_label", "")
        if final_label and final_label not in {a_label, b_label} and not row.get(
            "adjudication_notes", ""
        ):
            errors.append(f"row {number}: third-label choice requires notes")
        if row.get("resolution") == "PENDING_ADJUDICATION" and not final_label:
            errors.append(f"row {number}: unresolved conflict")

    if conflicts:
        if len(adjudicator_ids) != 1:
            errors.append(f"Expected one adjudicator id, got {sorted(adjudicator_ids)}")
        adjudicator_id = next(iter(adjudicator_ids), "")
        if adjudicator_id in {annotator_a, annotator_b}:
            errors.append("Adjudicator must differ from A and B")
    else:
        adjudicator_id = ""

    if any(row.get("resolution") == "PENDING_ADJUDICATION" for row in conflicts):
        # If adjudicated_label filled, still treat pending resolution as incomplete
        # unless all rows have labels.
        if any(not row.get("adjudicated_label") for row in conflicts):
            errors.append("Unresolved conflicts remain")

    if errors:
        print("BLIND_FINALIZATION_FAILED", file=sys.stderr)
        for error in errors[:100]:
            print(f"- {error}", file=sys.stderr)
        return 3

    evidence_ok = dual_human_evidence_complete(manifest)
    if not evidence_ok and not args.allow_provisional:
        print(
            "Refusing FROZEN_DUAL_HUMAN_ANNOTATED without dual-human evidence. "
            "Pass --allow-provisional to emit PROVISIONAL_AUTOMATED_REVIEW only.",
            file=sys.stderr,
        )
        return 4

    status = (
        "FROZEN_DUAL_HUMAN_ANNOTATED"
        if evidence_ok
        else "PROVISIONAL_AUTOMATED_REVIEW"
    )
    claim_allowed = bool(evidence_ok)
    completed_sha = sha256_file(conflicts_path)
    guide_sha = sha256_file(GUIDE_PATH) if GUIDE_PATH.exists() else None

    finals = []
    for row in agreements:
        finals.append(
            {
                "review_id": row.get("review_id", ""),
                "id": row["id"],
                "final_label": row["final_label"],
                "resolution": "AGREED",
                "human_annotator_ids": [annotator_a, annotator_b],
            }
        )
    for row in conflicts:
        finals.append(
            {
                "review_id": row.get("review_id", ""),
                "id": row["id"],
                "final_label": row["adjudicated_label"],
                "resolution": "ADJUDICATED",
                "human_annotator_ids": [
                    annotator_a,
                    annotator_b,
                    row["adjudicator_id"],
                ],
                "adjudication_notes": row.get("adjudication_notes", ""),
            }
        )

    overlay = {
        "version": "1.0.0",
        "status": status,
        "claim_allowed": claim_allowed,
        "dual_human_evidence_complete": evidence_ok,
        "count": len(finals),
        "final_label_distribution": dict(
            Counter(item["final_label"] for item in finals)
        ),
        "annotator_ids": [annotator_a, annotator_b],
        "adjudicator_id": adjudicator_id or None,
        "annotation_guide_sha256": guide_sha,
        "blank_conflicts_sha256": dual.get("blank_conflicts_sha256"),
        "completed_conflicts_sha256": completed_sha,
        "labels": finals,
    }
    overlay_path = pack_dir / "final_labels.json"
    overlay_path.write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest["status"] = status
    manifest["claim_allowed"] = claim_allowed
    manifest["dual_human_evidence_complete"] = evidence_ok
    manifest["annotation_guide_sha256"] = guide_sha
    manifest["dual_annotation"] = {
        **dual,
        "status": status,
        "completed_conflicts_sha256": completed_sha,
        "conflicts_sha256": completed_sha,
        "adjudicator_id": adjudicator_id or None,
    }
    manifest["final_labels"] = {
        "path": relpath(overlay_path),
        "sha256": sha256_file(overlay_path),
        "status": status,
        "claim_allowed": claim_allowed,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": status,
                "claim_allowed": claim_allowed,
                "dual_human_evidence_complete": evidence_ok,
                "count": len(finals),
                "completed_conflicts_sha256": completed_sha,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
