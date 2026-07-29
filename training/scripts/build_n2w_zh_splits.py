#!/usr/bin/env python3
"""Build Chinese-only processed splits for the normal_2w scheme.

train  = data/raw/normal_2w_zh_relabel.jsonl (deduped, all rows)
val/test = language=zh rows from annotated_homework_bootstrap.jsonl
           (deduped, 50/50 group-split, no overlap with train)

Does NOT merge synthetic or non-zh bootstrap rows into processed/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.deduplicate import deduplicate_exact, deduplicate_normalized  # noqa: E402
from src.leakage import audit_leakage  # noqa: E402
from src.schema import LABEL_ORDER, load_jsonl, write_jsonl  # noqa: E402
from src.split_groups import split_groups  # noqa: E402

TRAINABLE = set(LABEL_ORDER)
DEFAULT_TRAIN_RAW = ROOT / "data" / "raw" / "normal_2w_zh_relabel.jsonl"
DEFAULT_EVAL_RAW = ROOT / "data" / "raw" / "annotated_homework_bootstrap.jsonl"
DEFAULT_PROCESSED = ROOT / "data" / "processed"
DEFAULT_SUMMARY = ROOT / "data" / "manifests" / "normal_2w_zh_relabel_summary.json"
DEFAULT_MANIFEST = ROOT / "data" / "manifests" / "dataset_manifest.json"
DEFAULT_LEAKAGE = ROOT / "reports" / "metrics" / "dataset_leakage.json"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--train-raw", type=Path, default=DEFAULT_TRAIN_RAW)
    p.add_argument("--eval-raw", type=Path, default=DEFAULT_EVAL_RAW)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_PROCESSED)
    p.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--leakage-out", type=Path, default=DEFAULT_LEAKAGE)
    p.add_argument("--seed", type=int, default=42)
    return p


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def only_trainable(records):
    return [r for r in records if r.label in TRAINABLE]


def rel_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if not args.train_raw.exists():
        print(f"missing train raw: {args.train_raw}", file=sys.stderr)
        return 1
    if not args.eval_raw.exists():
        print(f"missing eval raw: {args.eval_raw}", file=sys.stderr)
        return 1

    train_raw = only_trainable(load_jsonl(args.train_raw))
    train, rem_exact_tr = deduplicate_exact(train_raw)
    train, rem_norm_tr = deduplicate_normalized(train)
    for r in train:
        r.split = "train"

    boot_all = load_jsonl(args.eval_raw)
    boot_zh = [r for r in boot_all if r.language == "zh" and r.label in TRAINABLE]
    n_zh_before = len(boot_zh)
    boot_zh, rem_exact_ev = deduplicate_exact(boot_zh)
    boot_zh, rem_norm_ev = deduplicate_normalized(boot_zh)

    train_texts = {r.text for r in train}
    train_ids = {r.id for r in train}
    before = len(boot_zh)
    boot_zh = [r for r in boot_zh if r.text not in train_texts and r.id not in train_ids]
    dropped_overlap = before - len(boot_zh)

    eval_splits = split_groups(boot_zh, ratios=(0.0, 0.5, 0.5), seed=args.seed)
    if eval_splits["train"]:
        print("internal error: eval train bucket not empty", file=sys.stderr)
        return 1
    validation = eval_splits["validation"]
    test = eval_splits["test"]
    for r in validation:
        r.split = "validation"
    for r in test:
        r.split = "test"

    flat = train + validation + test
    leakage = audit_leakage(flat)
    if leakage.get("status") != "PASS":
        print(json.dumps(leakage, ensure_ascii=False, indent=2), file=sys.stderr)
        print("Refusing to write splits with leakage.", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    split_map = {"train": train, "validation": validation, "test": test}
    split_hashes: Dict[str, dict] = {}
    for name, recs in split_map.items():
        out = args.output_dir / f"{name}.jsonl"
        write_jsonl(out, recs)
        split_hashes[name] = {
            "path": rel_to_root(out),
            "count": len(recs),
            "label_dist": dict(Counter(r.label for r in recs)),
            "language_dist": dict(Counter(r.language for r in recs)),
            "source_dist": dict(Counter(r.source for r in recs)),
            "sha256": sha256_file(out),
        }
        print(
            f"{name}: n={len(recs)} labels={split_hashes[name]['label_dist']} "
            f"langs={split_hashes[name]['language_dist']}"
        )

    summary = {
        "version": "1.1.0",
        "scheme": (
            "train=normal_2w_zh_relabel(all,deduped); "
            "val/test=annotated_homework_bootstrap zh-only 50/50 group-split"
        ),
        "seed": args.seed,
        "train": {
            "source_file": rel_to_root(args.train_raw),
            "n_before_dedupe": len(train_raw),
            "removed_exact": rem_exact_tr,
            "removed_normalized": rem_norm_tr,
            "n_after_dedupe": len(train),
            "label_dist": dict(Counter(r.label for r in train)),
        },
        "eval": {
            "source_file": rel_to_root(args.eval_raw),
            "filter": "language=zh and four-class labels only",
            "n_zh_trainable_before_dedupe": n_zh_before,
            "removed_exact": rem_exact_ev,
            "removed_normalized": rem_norm_ev,
            "dropped_overlap_with_train": dropped_overlap,
            "n_eval_pool": len(boot_zh),
            "split_ratios": {"validation": 0.5, "test": 0.5},
            "validation_count": len(validation),
            "test_count": len(test),
            "validation_label_dist": dict(Counter(r.label for r in validation)),
            "test_label_dist": dict(Counter(r.label for r in test)),
        },
        "splits": split_hashes,
        "leakage": leakage,
        "notes": [
            "en/hi/id from bootstrap excluded for Chinese-only phase",
            "synthetic_v2 not included in val/test",
            "eval labels are historical suggested annotations; cross-source probe only",
        ],
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "seed": args.seed,
        "scheme": summary["scheme"],
        "splits": {
            k: {"path": v["path"], "count": v["count"], "sha256": v["sha256"]}
            for k, v in split_hashes.items()
        },
        "dedupe": {
            "train_removed_exact": rem_exact_tr,
            "train_removed_normalized": rem_norm_tr,
            "eval_removed_exact": rem_exact_ev,
            "eval_removed_normalized": rem_norm_ev,
            "eval_dropped_overlap_with_train": dropped_overlap,
        },
        "leakage": leakage,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.leakage_out.parent.mkdir(parents=True, exist_ok=True)
    args.leakage_out.write_text(json.dumps(leakage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote summary → {args.summary}")
    print(f"Wrote manifest → {args.manifest}")
    print(f"Leakage: {leakage.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
