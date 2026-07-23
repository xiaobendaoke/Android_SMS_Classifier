#!/usr/bin/env python3
"""Report zh/en/hi/id × four-class gaps vs acceptance targets.

Compares:
  1) annotated_homework_bootstrap.jsonl (current trainable labeled pool)
  2) optional interim *_all_suggested.csv (includes NEEDS_REVIEW pool)

Targets (main spec §9.3):
  freeze_per_class = 500
  train_aspirational_per_class = 1000
  txn_special_per_language = 500

Outputs:
  training/reports/metrics/label_gap_report.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.schema import LABEL_ORDER, VALID_LANGUAGES  # noqa: E402

DEFAULT_ANNOTATED = ROOT / "data" / "raw" / "annotated_homework_bootstrap.jsonl"
DEFAULT_ANN_DIR = ROOT / "data" / "interim" / "annotation"
DEFAULT_OUT = ROOT / "reports" / "metrics" / "label_gap_report.json"

PACK_CSVS: List[Tuple[str, str]] = [
    ("zh_all_suggested.csv", "zh"),
    ("uci_all_suggested.csv", "en"),
    ("id_yudiwbs_all_suggested.csv", "id"),
    ("id_spamshield_all_suggested.csv", "id"),
    ("iiitd_all_suggested.csv", "hi"),
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Four-language × four-class label gap report.")
    p.add_argument("--annotated", type=Path, default=DEFAULT_ANNOTATED)
    p.add_argument("--ann-dir", type=Path, default=DEFAULT_ANN_DIR)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--freeze-per-class", type=int, default=500)
    p.add_argument("--train-per-class", type=int, default=1000)
    p.add_argument("--txn-per-lang", type=int, default=500)
    return p


def load_annotated_counts(path: Path) -> Dict[str, Counter]:
    counts: Dict[str, Counter] = defaultdict(Counter)
    if not path.exists():
        return counts
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        lang = str(row.get("language", "")).strip().lower()
        label = str(row.get("label", "")).strip().upper()
        if lang in VALID_LANGUAGES and label in LABEL_ORDER:
            counts[lang][label] += 1
    return counts


def load_csv_pools(ann_dir: Path) -> Dict[str, Dict[str, Counter]]:
    """Return {lang: {trainable: Counter, needs_review: int, by_source: ...}}."""
    trainable: Dict[str, Counter] = defaultdict(Counter)
    needs_review: Counter = Counter()
    by_source: Dict[str, Counter] = defaultdict(Counter)
    for filename, lang_fallback in PACK_CSVS:
        path = ann_dir / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                lang = (row.get("language") or lang_fallback).strip().lower() or lang_fallback
                label = (row.get("label") or "").strip().upper()
                source = (row.get("source") or filename).strip()
                by_source[lang][source] += 1
                if label in LABEL_ORDER:
                    trainable[lang][label] += 1
                elif label == "NEEDS_REVIEW":
                    needs_review[lang] += 1
    return {
        "trainable": trainable,
        "needs_review": needs_review,
        "by_source": by_source,
    }


def gap_matrix(
    have: Dict[str, Counter],
    target: int,
) -> Dict[str, Dict[str, dict]]:
    out: Dict[str, Dict[str, dict]] = {}
    for lang in sorted(VALID_LANGUAGES):
        out[lang] = {}
        for label in LABEL_ORDER:
            n = int(have.get(lang, Counter()).get(label, 0))
            short = max(0, target - n)
            out[lang][label] = {
                "have": n,
                "target": target,
                "shortfall": short,
                "ok": short == 0,
            }
    return out


def priority_queue(freeze_gaps: Dict[str, Dict[str, dict]]) -> List[dict]:
    items = []
    for lang, by_label in freeze_gaps.items():
        for label, cell in by_label.items():
            if cell["shortfall"] > 0:
                items.append(
                    {
                        "language": lang,
                        "label": label,
                        "shortfall": cell["shortfall"],
                        "have": cell["have"],
                        "target": cell["target"],
                    }
                )
    items.sort(key=lambda x: (-x["shortfall"], x["language"], x["label"]))
    return items


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    annotated = load_annotated_counts(args.annotated)
    pools = load_csv_pools(args.ann_dir)

    freeze_gaps = gap_matrix(annotated, args.freeze_per_class)
    train_gaps = gap_matrix(annotated, args.train_per_class)
    txn_special = {
        lang: {
            "have": int(annotated.get(lang, Counter()).get("TRANSACTION", 0)),
            "target": args.txn_per_lang,
            "shortfall": max(
                0, args.txn_per_lang - int(annotated.get(lang, Counter()).get("TRANSACTION", 0))
            ),
        }
        for lang in sorted(VALID_LANGUAGES)
    }

    report = {
        "version": "1.0.0",
        "note": (
            "Homework annotated pool vs acceptance targets. "
            "Freeze claim still requires dual-annotated dedicated freeze SHA."
        ),
        "annotated_path": str(args.annotated.as_posix()),
        "annotated_exists": args.annotated.exists(),
        "targets": {
            "freeze_per_class": args.freeze_per_class,
            "train_aspirational_per_class": args.train_per_class,
            "txn_special_per_language": args.txn_per_lang,
        },
        "annotated_counts": {lang: dict(annotated.get(lang, Counter())) for lang in sorted(VALID_LANGUAGES)},
        "csv_trainable_counts": {
            lang: dict(pools["trainable"].get(lang, Counter())) for lang in sorted(VALID_LANGUAGES)
        },
        "csv_needs_review_counts": dict(pools["needs_review"]),
        "freeze_gaps": freeze_gaps,
        "train_aspirational_gaps": train_gaps,
        "txn_special_gaps": txn_special,
        "priority_fill_order": priority_queue(freeze_gaps),
        "notes": [
            "hi pool is mostly Hinglish/en-IN (iiitd); Devanagari still required for real hi acceptance.",
            "en TRANSACTION is extremely scarce in UCI; need other EN transactional SMS sources.",
            "NEEDS_REVIEW rows in interim CSVs are the primary refill pool for gap packs.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {args.out}")
    print("\nFreeze shortfalls (target={}):".format(args.freeze_per_class))
    print(f"{'lang':<4} {'label':<12} {'have':>6} {'short':>6}")
    for item in report["priority_fill_order"]:
        print(
            f"{item['language']:<4} {item['label']:<12} {item['have']:>6} {item['shortfall']:>6}"
        )
    ok_cells = sum(
        1
        for lang in freeze_gaps
        for label in freeze_gaps[lang]
        if freeze_gaps[lang][label]["ok"]
    )
    print(f"\nFreeze cells OK: {ok_cells}/16")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
