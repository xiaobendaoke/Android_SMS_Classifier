#!/usr/bin/env python3
"""Build no-replacement split_assignment_v2 by removing text-quality failures.

Reads v1 processed splits as read-only. Does not rebalance, resplit, or replace.
Never prints test SMS bodies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.leakage import audit_leakage  # noqa: E402
from src.metrics import label_distribution, wilson_interval  # noqa: E402
from src.schema import SmsRecord, load_jsonl, write_jsonl  # noqa: E402
from src.split_assignment import (  # noqa: E402
    COMPONENT_ALGORITHM_VERSION,
    compute_freeze_sha256,
    sha256_file,
    sha256_ids,
)
from src.split_groups import connected_group_ids  # noqa: E402
from src.text_quality import (  # noqa: E402
    SCANNER_VERSION,
    classify_text_quality_reasons,
    text_quality_issues,
)

EXPECTED_V1 = {
    "validation_sha256": (
        "4487924f07ca074e6ff4d345b2c79e1e9ea8719decc8cd4e5518ac4346ae9632"
    ),
    "test_sha256": (
        "fa98aa85fdb3047d8e90fe3ab98dd923f9490cd160cc60c90926eef937c79781"
    ),
}


def relpath(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def git_revision() -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT.parent,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build no-replacement v2 freeze.")
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=ROOT / "data" / "processed",
        help="Read-only v1/current processed directory.",
    )
    parser.add_argument(
        "--parent-assignment",
        type=Path,
        default=ROOT / "data" / "manifests" / "split_assignment_v1.json",
    )
    parser.add_argument(
        "--quality-report",
        type=Path,
        default=ROOT / "reports" / "metrics" / "frozen_text_quality_v1.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "processed_v2",
    )
    parser.add_argument(
        "--assignment-output",
        type=Path,
        default=ROOT / "data" / "manifests" / "split_assignment_v2.json",
    )
    parser.add_argument(
        "--dataset-manifest-output",
        type=Path,
        default=ROOT / "data" / "manifests" / "dataset_manifest_v2.json",
    )
    parser.add_argument(
        "--leakage-output",
        type=Path,
        default=ROOT / "reports" / "metrics" / "dataset_leakage_v2.json",
    )
    parser.add_argument(
        "--audit-output",
        type=Path,
        default=ROOT / "reports" / "metrics" / "freeze_audit_v2.json",
    )
    parser.add_argument(
        "--v1-status-output",
        type=Path,
        default=ROOT / "data" / "manifests" / "freeze_status_v1.json",
    )
    return parser


def distribution_with_ci(records: Sequence[SmsRecord]) -> Dict[str, object]:
    labels = [record.label for record in records]
    counts = label_distribution(labels)
    total = len(labels)
    languages = dict(Counter(record.language for record in records))
    return {
        "count": total,
        "label_distribution": counts,
        "language_distribution": languages,
        "label_proportions_ci95": {
            label: {
                "count": counts.get(label, 0),
                "proportion": (counts.get(label, 0) / total) if total else 0.0,
                "wilson_ci95": list(wilson_interval(counts.get(label, 0), total)),
            }
            for label in ("TRANSACTION", "AD", "HARASS", "FRAUD")
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    processed = args.processed_dir.resolve()
    parent_path = args.parent_assignment.resolve()
    if not parent_path.exists():
        print(f"Missing parent assignment: {parent_path}", file=sys.stderr)
        return 1

    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    # Verify v1 identity SHAs before mutating anything (we only write v2 paths).
    for split_name, expected in (
        ("validation", EXPECTED_V1["validation_sha256"]),
        ("test", EXPECTED_V1["test_sha256"]),
    ):
        path = processed / f"{split_name}.jsonl"
        actual = sha256_file(path)
        if actual != expected:
            print(
                f"Refusing v2 build: v1 {split_name} SHA changed "
                f"(expected={expected}, actual={actual})",
                file=sys.stderr,
            )
            return 2
        if parent["splits"][split_name]["sha256"] != expected:
            print(
                f"Parent assignment {split_name} SHA mismatch.",
                file=sys.stderr,
            )
            return 2

    if not args.quality_report.exists():
        print(f"Missing quality report: {args.quality_report}", file=sys.stderr)
        return 1
    quality = json.loads(args.quality_report.read_text(encoding="utf-8"))

    removals: List[dict] = []
    remove_ids_by_split: Dict[str, set[str]] = {
        "validation": set(),
        "test": set(),
    }
    for row in quality.get("failures", []):
        if row.get("split") not in {"validation", "test"}:
            continue
        remove_ids_by_split[row["split"]].add(row["id"])
        removals.append(
            {
                "id": row["id"],
                "split": row["split"],
                "quality_reason": row.get("quality_reason"),
                "text_sha256": row.get("text_sha256"),
                "label": row.get("label"),
                "source": row.get("source"),
                "component_id": row.get("component_id"),
            }
        )

    if len(removals) != 9:
        print(
            f"Expected exactly 9 validation/test quality failures, found {len(removals)}",
            file=sys.stderr,
        )
        return 3
    if len(remove_ids_by_split["validation"]) != 4:
        print("Expected 4 validation removals.", file=sys.stderr)
        return 3
    if len(remove_ids_by_split["test"]) != 5:
        print("Expected 5 test removals.", file=sys.stderr)
        return 3

    splits: Dict[str, List[SmsRecord]] = {}
    old_shas = {}
    new_meta = {}
    for split_name in ("train", "validation", "test"):
        path = processed / f"{split_name}.jsonl"
        records = load_jsonl(path)
        old_shas[split_name] = sha256_file(path)
        if split_name == "train":
            kept = records
            # Train already quarantined corrupt rows; refuse any remaining failures.
            bad_train = [
                record.id
                for record in kept
                if classify_text_quality_reasons(record.text)
                or record.label == "NEEDS_REVIEW"
            ]
            if bad_train:
                print(
                    "Train still contains quality/NEEDS_REVIEW rows: "
                    + ", ".join(bad_train[:20]),
                    file=sys.stderr,
                )
                return 4
        else:
            remove_ids = remove_ids_by_split[split_name]
            kept = []
            seen_remove = set()
            for record in records:
                if record.id in remove_ids:
                    # Confirm mechanical rule still fails.
                    if not classify_text_quality_reasons(record.text):
                        print(
                            f"{record.id} listed for removal but passes quality.",
                            file=sys.stderr,
                        )
                        return 5
                    seen_remove.add(record.id)
                    continue
                if classify_text_quality_reasons(record.text):
                    print(
                        f"Unexpected quality failure remains in {split_name}: "
                        f"{record.id}",
                        file=sys.stderr,
                    )
                    return 5
                if record.label == "NEEDS_REVIEW":
                    print(
                        f"NEEDS_REVIEW not allowed in {split_name}: {record.id}",
                        file=sys.stderr,
                    )
                    return 5
                kept.append(record)
            if seen_remove != remove_ids:
                print(
                    f"{split_name}: removal ID mismatch "
                    f"{sorted(remove_ids - seen_remove)}",
                    file=sys.stderr,
                )
                return 5
            # Remaining IDs must keep relative order from v1.
            expected_ids = [
                rid
                for rid in parent["splits"][split_name]["ids"]
                if rid not in remove_ids
            ]
            # Parent assignment may be pre-correction train identity; for
            # validation/test, parent IDs match frozen identity.
            actual_ids = [record.id for record in kept]
            if actual_ids != expected_ids:
                # Fallback: ensure kept IDs equal processed order minus removals.
                processed_expected = [
                    record.id for record in records if record.id not in remove_ids
                ]
                if actual_ids != processed_expected:
                    print(f"{split_name}: remaining ID order changed.", file=sys.stderr)
                    return 6
        for record in kept:
            record.split = split_name
        splits[split_name] = kept

    # No component migration / rebalancing: membership is only deletions.
    flat = []
    for split_name in ("train", "validation", "test"):
        flat.extend(splits[split_name])
    leakage = audit_leakage(flat)
    if leakage["status"] != "PASS":
        print(json.dumps(leakage, indent=2, ensure_ascii=False), file=sys.stderr)
        return 7

    args.output_dir.mkdir(parents=True, exist_ok=True)
    split_payload = {}
    for split_name in ("train", "validation", "test"):
        out_path = args.output_dir / f"{split_name}.jsonl"
        write_jsonl(out_path, splits[split_name])
        records = splits[split_name]
        components = connected_group_ids(records)
        ids = [record.id for record in records]
        stats = distribution_with_ci(records)
        split_payload[split_name] = {
            "count": len(ids),
            "sha256": sha256_file(out_path),
            "ids_sha256": sha256_ids(ids),
            "ids": ids,
            "component_ids": sorted({components[i] for i in range(len(records))}),
            "id_to_component": {
                records[i].id: components[i] for i in range(len(records))
            },
            "label_distribution": stats["label_distribution"],
            "language_distribution": stats["language_distribution"],
            "label_proportions_ci95": stats["label_proportions_ci95"],
            "path": relpath(out_path),
            "parent_sha256": old_shas[split_name],
        }
        new_meta[split_name] = split_payload[split_name]

    assignment = {
        "version": "2.0.0",
        "seed": parent.get("seed", 42),
        "parent_assignment": relpath(parent_path),
        "parent_assignment_sha256": sha256_file(parent_path),
        "parent_freeze_sha256": parent.get("freeze_sha256"),
        "source_shas": parent.get("source_shas", []),
        "holdout_ids_sha256": parent.get("holdout_ids_sha256"),
        "holdout_manifest_sha256": parent.get("holdout_manifest_sha256"),
        "component_algorithm_version": COMPONENT_ALGORITHM_VERSION,
        "removal_policy": "text_quality_only",
        "replacement_policy": "none",
        "model_scores_used": False,
        "claim_allowed": False,
        "scanner_version": SCANNER_VERSION,
        "removed_corrupt": removals,
        "removed_counts": {
            "validation": len(remove_ids_by_split["validation"]),
            "test": len(remove_ids_by_split["test"]),
            "total": len(removals),
        },
        "replacement_ids": [],
        "replacement_annotation_manifest_sha256": None,
        "splits": split_payload,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_revision": git_revision(),
        "status": "FROZEN_TEXT_QUALITY_V2",
    }
    # freeze_sha256 uses shared helper fields plus v2 version.
    assignment["freeze_sha256"] = compute_freeze_sha256(assignment)

    args.assignment_output.parent.mkdir(parents=True, exist_ok=True)
    args.assignment_output.write_text(
        json.dumps(assignment, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    args.leakage_output.parent.mkdir(parents=True, exist_ok=True)
    args.leakage_output.write_text(
        json.dumps(leakage, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    dataset_manifest = {
        "status": "FROZEN_FOR_TRAINING_V2",
        "version": "2.0.0",
        "claim_allowed": False,
        "freeze_sha256": assignment["freeze_sha256"],
        "split_assignment": relpath(args.assignment_output),
        "parent_assignment_sha256": assignment["parent_assignment_sha256"],
        "removal_policy": "text_quality_only",
        "replacement_policy": "none",
        "model_scores_used": False,
        "seed": assignment["seed"],
        "source_files": assignment["source_shas"],
        "splits": {
            name: {
                "path": new_meta[name]["path"],
                "count": new_meta[name]["count"],
                "sha256": new_meta[name]["sha256"],
                "parent_sha256": new_meta[name]["parent_sha256"],
                "label_distribution": new_meta[name]["label_distribution"],
                "language_distribution": new_meta[name]["language_distribution"],
                "label_proportions_ci95": new_meta[name]["label_proportions_ci95"],
            }
            for name in ("train", "validation", "test")
        },
        "removed_corrupt": removals,
        "leakage": leakage,
        "blockers": [
            {
                "type": "human_annotation_incomplete",
                "note": (
                    "Dual-human annotation packs are pending. claim_allowed remains "
                    "false until provenance closes."
                ),
            }
        ],
        "generated_at": assignment["generated_at"],
    }
    args.dataset_manifest_output.write_text(
        json.dumps(dataset_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    audit = {
        "status": "PASS",
        "removal_policy": "text_quality_only",
        "replacement_policy": "none",
        "model_scores_used": False,
        "claim_allowed": False,
        "parent_validation_sha256": old_shas["validation"],
        "parent_test_sha256": old_shas["test"],
        "v2_validation_sha256": new_meta["validation"]["sha256"],
        "v2_test_sha256": new_meta["test"]["sha256"],
        "removed_counts": assignment["removed_counts"],
        "removed_ids": {
            "validation": sorted(remove_ids_by_split["validation"]),
            "test": sorted(remove_ids_by_split["test"]),
        },
        "counts": {
            name: new_meta[name]["count"] for name in ("train", "validation", "test")
        },
        "label_distributions": {
            name: new_meta[name]["label_distribution"]
            for name in ("train", "validation", "test")
        },
        "assignment_path": relpath(args.assignment_output),
        "assignment_freeze_sha256": assignment["freeze_sha256"],
        "recomputed_freeze_sha256": compute_freeze_sha256(assignment),
    }
    args.audit_output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Sidecar only — never rewrite v1 assignment / dataset_manifest content.
    v1_status = {
        "status": "SUPERSEDED_DUE_TO_TEXT_QUALITY",
        "claim_allowed": False,
        "superseded_by": relpath(args.assignment_output),
        "blocker_count": 9,
        "validation_sha256": EXPECTED_V1["validation_sha256"],
        "test_sha256": EXPECTED_V1["test_sha256"],
        "parent_assignment": relpath(parent_path),
        "parent_assignment_sha256": sha256_file(parent_path),
        "quality_report": relpath(args.quality_report),
        "note": (
            "v1 validation/test files and SHAs remain immutable. Use v2 for "
            "future validation-only work after human packs complete."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    args.v1_status_output.write_text(
        json.dumps(v1_status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Final silent integrity: v1 files unchanged.
    if sha256_file(processed / "validation.jsonl") != EXPECTED_V1["validation_sha256"]:
        print("v1 validation mutated during v2 build.", file=sys.stderr)
        return 8
    if sha256_file(processed / "test.jsonl") != EXPECTED_V1["test_sha256"]:
        print("v1 test mutated during v2 build.", file=sys.stderr)
        return 8

    print(
        json.dumps(
            {
                "status": "FROZEN_TEXT_QUALITY_V2",
                "claim_allowed": False,
                "counts": audit["counts"],
                "removed_counts": audit["removed_counts"],
                "v2_validation_sha256": audit["v2_validation_sha256"],
                "v2_test_sha256": audit["v2_test_sha256"],
                "assignment": audit["assignment_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
