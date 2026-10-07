#!/usr/bin/env python3
"""Generate a deterministic train-only representative calibration manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "configs" / "quantization.yaml"

sys.path.insert(0, str(ROOT))
from src.schema import LABEL_ORDER, SmsRecord, load_jsonl, write_jsonl  # noqa: E402
from src.train_utils import write_json  # noqa: E402


def length_bucket(text: str) -> str:
    size = len(text.encode("utf-8"))
    if size <= 80:
        return "short"
    if size <= 200:
        return "medium"
    return "long"


def stable_key(record: SmsRecord, seed: int) -> str:
    return hashlib.sha256(f"{seed}\0{record.id}".encode("utf-8")).hexdigest()


def stratified_sample(records: Sequence[SmsRecord], target: int, seed: int) -> List[SmsRecord]:
    """Round-robin deterministic strata across label/source/UTF-8 length."""
    cells: Dict[Tuple[str, str, str], List[SmsRecord]] = defaultdict(list)
    for record in records:
        if record.split == "train" and record.label in LABEL_ORDER:
            cells[(record.label, record.source, length_bucket(record.text))].append(record)
    for pool in cells.values():
        pool.sort(key=lambda record: stable_key(record, seed))

    selected: List[SmsRecord] = []
    ordered_cells = sorted(cells)
    offset = 0
    while len(selected) < target:
        added = False
        for cell in ordered_cells:
            pool = cells[cell]
            if offset < len(pool):
                selected.append(pool[offset])
                added = True
                if len(selected) == target:
                    break
        if not added:
            break
        offset += 1
    return selected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a deterministic representative manifest from train only."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--train", type=Path, default=ROOT / "data" / "processed" / "train.jsonl"
    )
    parser.add_argument("--output", type=Path, help="Overrides representative.manifest.")
    parser.add_argument("--num-samples", type=int, help="Overrides representative.num_samples.")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--summary", type=Path, help="Optional generation summary JSON.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.config.exists():
        print(f"Config missing: {args.config}", file=sys.stderr)
        return 1
    import yaml

    with args.config.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    rep_cfg = cfg.get("representative", {})
    output = args.output or ROOT / rep_cfg.get(
        "manifest", "data/processed/representative.jsonl"
    )
    target = args.num_samples or int(rep_cfg.get("num_samples", 800))
    seed = args.seed if args.seed is not None else int(cfg.get("seed", 42))
    if target <= 0:
        print("--num-samples must be positive", file=sys.stderr)
        return 1
    if not args.train.exists():
        print(f"Train manifest missing: {args.train}", file=sys.stderr)
        return 1

    records = load_jsonl(args.train)
    selected = stratified_sample(records, target, seed)
    if not selected:
        print("No eligible train records found.", file=sys.stderr)
        return 1
    write_jsonl(output, selected)
    distribution = {
        "label": dict(sorted(Counter(r.label for r in selected).items())),
        "source": dict(sorted(Counter(r.source for r in selected).items())),
        "length_bucket": dict(sorted(Counter(length_bucket(r.text) for r in selected).items())),
    }
    summary = {
        "input": str(args.train),
        "output": str(output),
        "seed": seed,
        "requested_samples": target,
        "selected_samples": len(selected),
        "train_only": all(r.split == "train" for r in selected),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "distribution": distribution,
    }
    if args.summary:
        write_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
