#!/usr/bin/env python3
"""Build processed train/validation/test datasets."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import List, Optional

SEED = 42

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"

sys.path.insert(0, str(ROOT))
from src.augment import augment_text  # noqa: E402
from src.deduplicate import deduplicate_exact, deduplicate_normalized  # noqa: E402
from src.leakage import audit_leakage  # noqa: E402
from src.schema import SmsRecord, load_jsonl, write_jsonl  # noqa: E402
from src.split_groups import split_groups  # noqa: E402
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
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    return parser


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def load_raw_records(raw_dir: Path) -> List[SmsRecord]:
    records: List[SmsRecord] = []
    for path in sorted(raw_dir.glob("*.jsonl")):
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


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    set_seed(args.seed)
    removed_exact = removed_norm = 0

    if args.use_processed:
        if not args.output_dir.exists():
            print(f"Processed directory missing: {args.output_dir}", file=sys.stderr)
            return 1
        records = load_processed_pool(args.output_dir)
        if not records:
            print("No records found in processed directory.", file=sys.stderr)
            return 1
        # Re-assign splits via group split (clears any prior leaky assignment).
        for record in records:
            record.split = "train"
            record.parent_id = None
            record.is_adversarial = False
        records, removed_exact = deduplicate_exact(records)
        records, removed_norm = deduplicate_normalized(records)
        splits = split_groups(records, seed=args.seed)
    elif args.raw_dir.exists() and any(args.raw_dir.glob("*.jsonl")):
        records = load_raw_records(args.raw_dir)
        if not records:
            print(f"No JSONL records in {args.raw_dir}", file=sys.stderr)
            return 1
        records, removed_exact = deduplicate_exact(records)
        records, removed_norm = deduplicate_normalized(records)
        splits = split_groups(records, seed=args.seed)
    else:
        print(
            f"Raw data missing: {args.raw_dir}. "
            "Run generate_synthetic_dataset.py first (writes raw only).",
            file=sys.stderr,
        )
        return 1

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
    split_hashes = {}
    for split_name in ("train", "validation", "test"):
        out_path = args.output_dir / f"{split_name}.jsonl"
        write_jsonl(out_path, splits.get(split_name, []))
        split_hashes[split_name] = {
            "path": str(out_path.relative_to(ROOT)).replace("\\", "/"),
            "count": len(splits.get(split_name, [])),
            "sha256": sha256_file(out_path),
        }

    manifest_path = ROOT / "data" / "manifests" / "dataset_manifest.json"
    leakage_path = ROOT / "reports" / "metrics" / "dataset_leakage.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    leakage_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "seed": args.seed,
        "splits": split_hashes,
        "dedupe": {
            "removed_exact": removed_exact,
            "removed_normalized": removed_norm,
        },
        "leakage": leakage,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    leakage_path.write_text(
        json.dumps(leakage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote splits to {args.output_dir}")
    print(f"Wrote manifest to {manifest_path}")
    print(f"Leakage audit PASS → {leakage_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
