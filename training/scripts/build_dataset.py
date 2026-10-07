#!/usr/bin/env python3
"""Build processed train/validation/test datasets from a frozen split assignment."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence

SEED = 42

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

sys.path.insert(0, str(ROOT))
from src.augment import augment_text  # noqa: E402
from src.deduplicate import deduplicate_exact, deduplicate_normalized  # noqa: E402
from src.label_corrections import apply_train_only_corrections  # noqa: E402
from src.leakage import audit_leakage  # noqa: E402
from src.schema import SmsRecord, load_jsonl, write_jsonl  # noqa: E402
from src.split_assignment import (  # noqa: E402
    apply_frozen_assignment,
    load_assignment,
    sha256_file,
    verify_split_file_against_assignment,
)
from src.split_groups import connected_group_ids, split_groups  # noqa: E402
from src.train_utils import set_seed  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build dataset JSONL splits.")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=ROOT / "data" / "raw",
        help="Raw data directory (JSONL files).",
    )
    parser.add_argument(
        "--raw-file",
        type=Path,
        action="append",
        default=[],
        help="Explicit raw JSONL file; repeat to avoid loading every file in --raw-dir.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROCESSED,
        help="Output directory for JSONL files.",
    )
    parser.add_argument(
        "--use-processed",
        action="store_true",
        help="Load existing processed splits instead of raw input.",
    )
    parser.add_argument(
        "--augment-train",
        action="store_true",
        help="Apply train-only augmentation after dedupe/split.",
    )
    parser.add_argument(
        "--holdout-manifest",
        type=Path,
        default=ROOT / "data" / "manifests" / "transaction_specialist_holdout.json",
        help=(
            "Optional JSON containing reserved ids. Entire connected components "
            "are excluded before splitting."
        ),
    )
    parser.add_argument(
        "--label-corrections",
        type=Path,
        default=ROOT / "data" / "manifests" / "boundary_label_corrections_v1.json",
        help="Optional frozen/provisional human label-correction overlay.",
    )
    parser.add_argument(
        "--split-assignment",
        type=Path,
        default=ROOT / "data" / "manifests" / "split_assignment_v1.json",
        help="Immutable split assignment manifest. Required unless --allow-legacy-resplit.",
    )
    parser.add_argument(
        "--forced-quarantine",
        type=Path,
        default=ROOT / "data" / "manifests" / "forced_quarantine_v1.json",
        help="IDs forced into NEEDS_REVIEW quarantine (train-only).",
    )
    parser.add_argument(
        "--allow-legacy-resplit",
        action="store_true",
        help=(
            "Dangerous: re-run automatic split_groups. Forbidden for formal rebuilds "
            "once split_assignment_v1.json exists."
        ),
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    return parser


def load_raw_records(raw_dir: Path, raw_files: Sequence[Path] = ()) -> List[SmsRecord]:
    records: List[SmsRecord] = []
    paths = list(raw_files) if raw_files else sorted(raw_dir.glob("*.jsonl"))
    for path in paths:
        records.extend(load_jsonl(path))
    return records


def load_processed_pool(processed_dir: Path) -> List[SmsRecord]:
    records: List[SmsRecord] = []
    for split in ("train", "validation", "test"):
        path = processed_dir / f"{split}.jsonl"
        if path.exists():
            records.extend(load_jsonl(path))
    return records


def augment_train_records(records: List[SmsRecord], seed: int) -> List[SmsRecord]:
    augmented: List[SmsRecord] = list(records)
    for idx, record in enumerate(records):
        for v_idx, variant in enumerate(augment_text(record.text, seed=seed + idx)):
            augmented.append(
                SmsRecord(
                    id=f"{record.id}-aug-{v_idx}",
                    text=variant,
                    label=record.label,
                    language=record.language,
                    source=record.source,
                    source_license=record.source_license,
                    sender_group=record.sender_group,
                    template_group=record.template_group,
                    split="train",
                    is_synthetic=record.is_synthetic,
                    is_adversarial=True,
                    parent_id=record.id,
                    annotator_ids=["augment"],
                )
            )
    return augmented


def load_holdout_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    ids = payload.get("ids", []) if isinstance(payload, dict) else payload
    if not isinstance(ids, list):
        raise ValueError(f"holdout manifest ids must be a list: {path}")
    return {str(item) for item in ids if str(item)}


def exclude_holdout_components(
    records: List[SmsRecord],
    holdout_ids: set[str],
) -> tuple[List[SmsRecord], int]:
    """Exclude every record connected to any reserved holdout ID."""
    if not holdout_ids:
        return records, 0
    component_ids = connected_group_ids(records)
    held_components = {
        component_ids[idx]
        for idx, record in enumerate(records)
        if record.id in holdout_ids
    }
    kept = [
        record
        for idx, record in enumerate(records)
        if component_ids[idx] not in held_components
    ]
    return kept, len(records) - len(kept)


def load_forced_quarantine_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    ids = payload.get("ids", [])
    return {str(item) for item in ids if str(item)}


def apply_label_corrections(
    records: List[SmsRecord],
    path: Path,
) -> tuple[List[SmsRecord], dict]:
    """Compatibility wrapper used by unit tests.

    Formal builds must use frozen assignment + apply_train_only_corrections.
    This helper still applies overlays before any split and is only for tests /
    emergency legacy paths.
    """
    from src.label_corrections import (
        STATUS_APPLIED,
        STATUS_REMOVED_NEEDS_REVIEW,
        STATUS_UNMATCHED,
        load_corrections_manifest,
        text_sha256,
    )

    if not path.exists():
        return records, {
            "manifest": None,
            "applied_ids": 0,
            "changed_labels": 0,
            "removed_needs_review": 0,
        }
    payload = load_corrections_manifest(path)
    corrections = payload.get("corrections", [])
    by_id = {str(item.get("id", "")): item for item in corrections}
    applied_ids: set[str] = set()
    changed_labels = 0
    removed_needs_review = 0
    kept: List[SmsRecord] = []
    unmatched: List[str] = []
    for record in records:
        correction = by_id.get(record.id)
        if correction is None:
            kept.append(record)
            continue
        expected = str(correction.get("text_sha256", ""))
        if expected and text_sha256(record.text) != expected:
            kept.append(record)
            unmatched.append(record.id)
            continue
        applied_ids.add(record.id)
        final_label = str(correction.get("final_label", ""))
        if final_label == "NEEDS_REVIEW":
            removed_needs_review += 1
            continue
        if final_label not in {"TRANSACTION", "AD", "HARASS", "FRAUD"}:
            raise ValueError(f"Invalid corrected label for {record.id}: {final_label!r}")
        if record.label != final_label:
            changed_labels += 1
        record.label = final_label
        record.annotator_ids = list(
            dict.fromkeys(
                [
                    *record.annotator_ids,
                    *[
                        str(value)
                        for value in correction.get("human_annotator_ids", [])
                        if str(value)
                    ],
                ]
            )
        )
        kept.append(record)
    missing = sorted(set(by_id) - applied_ids - set(unmatched))
    unmatched.extend(missing)
    try:
        manifest_display = str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        manifest_display = str(path).replace("\\", "/")
    return kept, {
        "manifest": manifest_display,
        "manifest_sha256": sha256_file(path),
        "applied_ids": len(applied_ids),
        "changed_labels": changed_labels,
        "removed_needs_review": removed_needs_review,
        "unmatched_ids": sorted(set(unmatched)),
        "unmatched_count": len(set(unmatched)),
        "statuses": {
            STATUS_APPLIED: len(applied_ids),
            STATUS_REMOVED_NEEDS_REVIEW: removed_needs_review,
            STATUS_UNMATCHED: len(set(unmatched)),
        },
        "manifest_status": payload.get("status"),
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    args.holdout_manifest = args.holdout_manifest.resolve()
    args.label_corrections = args.label_corrections.resolve()
    args.split_assignment = args.split_assignment.resolve()
    args.forced_quarantine = args.forced_quarantine.resolve()
    args.raw_file = [path.resolve() for path in args.raw_file]
    set_seed(args.seed)
    removed_exact = removed_norm = 0
    removed_holdout = 0
    correction_stats: dict = {}
    correction_details: list = []

    if args.use_processed:
        if not args.output_dir.exists():
            print(f"Processed directory missing: {args.output_dir}", file=sys.stderr)
            return 1
        records = load_processed_pool(args.output_dir)
        if not records:
            print("No records found in processed directory.", file=sys.stderr)
            return 1
        for record in records:
            record.split = "train"
        records = [record for record in records if not record.is_adversarial]
    elif args.raw_file or (args.raw_dir.exists() and any(args.raw_dir.glob("*.jsonl"))):
        records = load_raw_records(args.raw_dir, args.raw_file)
        if not records:
            print(f"No JSONL records in {args.raw_dir}", file=sys.stderr)
            return 1
    else:
        print(
            f"Raw data missing: {args.raw_dir}. "
            "Run generate_synthetic_dataset.py first (writes raw only).",
            file=sys.stderr,
        )
        return 1

    records, removed_exact = deduplicate_exact(records)
    records, removed_norm = deduplicate_normalized(records)
    holdout_ids = load_holdout_ids(args.holdout_manifest)
    records, removed_holdout = exclude_holdout_components(records, holdout_ids)

    using_frozen = args.split_assignment.exists() and not args.allow_legacy_resplit
    if args.split_assignment.exists() and args.allow_legacy_resplit:
        print(
            "Refusing --allow-legacy-resplit while split assignment exists.",
            file=sys.stderr,
        )
        return 2
    if not using_frozen:
        if not args.allow_legacy_resplit:
            print(
                f"Missing frozen split assignment: {args.split_assignment}. "
                "Run restore_pre_boundary_split.py and freeze_split_assignment.py first.",
                file=sys.stderr,
            )
            return 2
        # Legacy path only for synthetic bootstrap tests.
        if args.label_corrections.exists():
            records, correction_stats = apply_label_corrections(
                records, args.label_corrections
            )
        splits = split_groups(records, seed=args.seed)
        assignment = None
    else:
        assignment = load_assignment(args.split_assignment)
        splits = apply_frozen_assignment(records, assignment)
        if args.label_corrections.exists():
            forced_ids = load_forced_quarantine_ids(args.forced_quarantine)
            splits, correction_details, correction_stats = apply_train_only_corrections(
                splits,
                args.label_corrections,
                forced_quarantine_ids=forced_ids,
                quarantine_text_failures=True,
            )
            try:
                correction_stats["manifest"] = str(
                    args.label_corrections.relative_to(ROOT)
                ).replace("\\", "/")
            except ValueError:
                pass
            correction_stats["manifest_sha256"] = sha256_file(args.label_corrections)

    if args.augment_train:
        splits["train"] = augment_train_records(splits.get("train", []), args.seed)

    flat: List[SmsRecord] = []
    for split_name in ("train", "validation", "test"):
        for record in splits.get(split_name, []):
            record.split = split_name
            flat.append(record)
    leakage = audit_leakage(flat)
    if leakage["status"] != "PASS":
        print(json.dumps(leakage, indent=2, ensure_ascii=False), file=sys.stderr)
        print("Refusing to write splits with leakage.", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir = ROOT / "data" / "interim" / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    split_hashes = {}
    for split_name in ("train", "validation", "test"):
        out_path = args.output_dir / f"{split_name}.jsonl"
        write_jsonl(out_path, splits.get(split_name, []))
        split_hashes[split_name] = {
            "path": str(out_path.relative_to(ROOT)).replace("\\", "/"),
            "count": len(splits.get(split_name, [])),
            "sha256": sha256_file(out_path),
        }

    quarantine_records = list(splits.get("quarantine", []))
    quarantine_path = quarantine_dir / "train_quarantine_v1.jsonl"
    write_jsonl(quarantine_path, quarantine_records)

    if assignment is not None:
        # Validation/test identity must remain byte-identical to the freeze.
        for split_name in ("validation", "test"):
            errors = verify_split_file_against_assignment(
                args.output_dir / f"{split_name}.jsonl",
                assignment,
                split_name,
            )
            if errors:
                print(
                    "Frozen validation/test identity broken:\n- "
                    + "\n- ".join(errors),
                    file=sys.stderr,
                )
                return 4

    details_path = (
        ROOT / "data" / "manifests" / "boundary_correction_application_v1.json"
    )
    details_payload = {
        "status": correction_stats.get("manifest_status"),
        "claim_allowed": correction_stats.get("claim_allowed", False),
        "stats": {
            key: correction_stats.get(key)
            for key in (
                "applied",
                "removed_needs_review",
                "unmatched",
                "quarantined",
                "changed_labels",
                "unmatched_by_reason",
            )
            if key in correction_stats
        },
        "details": correction_details,
        "quarantine_path": str(quarantine_path.relative_to(ROOT)).replace("\\", "/"),
        "quarantine_count": len(quarantine_records),
    }
    details_path.write_text(
        json.dumps(details_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    holdout_sha = (
        sha256_file(args.holdout_manifest) if args.holdout_manifest.exists() else None
    )
    freeze_payload = {
        "seed": args.seed,
        "splits": {name: item["sha256"] for name, item in split_hashes.items()},
        "holdout_manifest_sha256": holdout_sha,
        "label_corrections_sha256": correction_stats.get("manifest_sha256"),
        "split_assignment_sha256": (
            sha256_file(args.split_assignment) if assignment is not None else None
        ),
    }
    freeze_sha256 = hashlib.sha256(
        json.dumps(freeze_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

    manifest_path = ROOT / "data" / "manifests" / "dataset_manifest.json"
    leakage_path = ROOT / "reports" / "metrics" / "dataset_leakage.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    leakage_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "status": "FROZEN_FOR_TRAINING",
        "freeze_sha256": freeze_sha256,
        "seed": args.seed,
        "split_assignment": (
            str(args.split_assignment.relative_to(ROOT)).replace("\\", "/")
            if assignment is not None
            else None
        ),
        "split_assignment_freeze_sha256": (
            assignment.get("freeze_sha256") if assignment is not None else None
        ),
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256_file(path),
            }
            for path in args.raw_file
        ],
        "splits": split_hashes,
        "dedupe": {
            "removed_exact": removed_exact,
            "removed_normalized": removed_norm,
        },
        "holdout": {
            "manifest": (
                str(args.holdout_manifest.relative_to(ROOT)).replace("\\", "/")
                if args.holdout_manifest.exists()
                else None
            ),
            "manifest_sha256": holdout_sha,
            "excluded_connected_records": removed_holdout,
        },
        "label_corrections": correction_stats,
        "correction_application": {
            "path": str(details_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(details_path),
        },
        "quarantine": {
            "path": str(quarantine_path.relative_to(ROOT)).replace("\\", "/"),
            "count": len(quarantine_records),
            "sha256": sha256_file(quarantine_path),
        },
        "leakage": leakage,
        "blockers": [],
    }
    # Known identity freeze may still contain unrecovered corrupt validation/test
    # rows; surface that without mutating locked SHAs.
    from src.text_quality import text_quality_issues

    for split_name in ("validation", "test"):
        corrupt = [
            record.id
            for record in splits.get(split_name, [])
            if text_quality_issues(record.text, record_id=record.id)
        ]
        if corrupt:
            manifest["blockers"].append(
                {
                    "type": "frozen_split_text_quality",
                    "split": split_name,
                    "count": len(corrupt),
                    "ids": corrupt,
                    "note": (
                        "Frozen identity SHA preserved; texts are unrecovered. "
                        "Do not claim validation-ready until resolved."
                    ),
                }
            )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    leakage_path.write_text(
        json.dumps(leakage, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote splits to {args.output_dir}")
    print(f"Wrote manifest to {manifest_path}")
    print(f"Leakage audit PASS → {leakage_path}")
    if manifest["blockers"]:
        print(
            json.dumps({"blockers": manifest["blockers"]}, ensure_ascii=False, indent=2)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
