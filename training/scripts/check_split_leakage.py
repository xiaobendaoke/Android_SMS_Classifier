#!/usr/bin/env python3
"""Fail if train/validation/test have ID or template-group leakage."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

SEED = 42
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.leakage import audit_leakage  # noqa: E402
from src.schema import load_jsonl  # noqa: E402
from src.train_utils import set_seed, write_json  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect ID / template_group leakage across dataset splits."
    )
    parser.add_argument(
        "--processed-dir",
        "--input-dir",
        dest="processed_dir",
        type=Path,
        default=ROOT / "data" / "processed",
        help="Directory containing train/validation/test JSONL.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "metrics" / "dataset_leakage.json",
        help="Leakage audit JSON output.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed (unused, for CLI parity).")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    set_seed(args.seed)

    records = []
    for split in ("train", "validation", "test"):
        path = args.processed_dir / f"{split}.jsonl"
        if not path.exists():
            print(f"Missing split: {path}", file=sys.stderr)
            return 1
        split_records = load_jsonl(path)
        for record in split_records:
            record.split = split
        records.extend(split_records)

    report = audit_leakage(records)
    write_json(args.output, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] != "PASS":
        print("Leakage detected — refuse to treat this dataset as frozen.", file=sys.stderr)
        return 1
    print(f"Leakage audit PASS → {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
