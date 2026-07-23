#!/usr/bin/env python3
"""Prepare human-review packs from permissively licensed web candidates.

The source labels are weak/predicted labels. This script never copies them into
the final ``label`` column, so these rows cannot silently enter training.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Sequence

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = (
    ROOT / "data" / "raw" / "hf_sms_otp_phishing_10k" / "sample_10k.csv"
)
DEFAULT_OUT_DIR = ROOT / "data" / "interim" / "annotation"
DEFAULT_SUMMARY = ROOT / "data" / "manifests" / "web_candidate_summary.json"

SOURCE_ID = "hf_sms_otp_phishing_10k"
FIELDNAMES = [
    "id",
    "text",
    "language",
    "source",
    "orig_label",
    "suggested_label",
    "suggest_reason",
    "label",
    "annotator",
    "template_group",
    "notes",
]


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def template_group(text: str) -> str:
    key = text.lower()
    key = re.sub(r"https?://\S+|www\.\S+", "<url>", key)
    key = re.sub(r"\b\d+\b", "#", key)
    key = re.sub(r"\s+", " ", key).strip()[:160]
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def suggest(row: Dict[str, str]) -> tuple[str, str]:
    if _truthy(row.get("is_phishing_original", "")):
        return "FRAUD", "source-predicted-phishing"
    if _truthy(row.get("predicted_is_otp", "")):
        return "TRANSACTION", "source-predicted-legitimate-otp"
    return "NEEDS_REVIEW", "source-success-but-not-otp-or-phishing"


def load_candidates(path: Path) -> tuple[List[dict], Counter]:
    records: List[dict] = []
    stats: Counter = Counter()
    seen_text: set[str] = set()

    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row_number, row in enumerate(csv.DictReader(fh), start=2):
            stats["input_rows"] += 1
            if row.get("classification_status", "").strip().lower() != "success":
                stats["excluded_non_success"] += 1
                continue
            text = (row.get("sms_text") or "").strip()
            if not text:
                stats["excluded_empty"] += 1
                continue
            if text in seen_text:
                stats["excluded_exact_duplicate"] += 1
                continue
            seen_text.add(text)

            suggested, reason = suggest(row)
            original_index = (row.get("original_index") or str(row_number)).strip()
            records.append(
                {
                    "id": f"en_otp_web_{original_index}",
                    "text": text,
                    "language": "en",
                    "source": SOURCE_ID,
                    "orig_label": (
                        f"otp={row.get('predicted_is_otp', '')};"
                        f"intent={row.get('predicted_otp_intent', '')};"
                        f"phishing={row.get('is_phishing_original', '')}"
                    ),
                    "suggested_label": suggested,
                    "suggest_reason": reason,
                    "label": "",
                    "annotator": "",
                    "template_group": template_group(text),
                    "notes": "weak-label;human-review-required;sender-not-exported",
                }
            )
            stats[f"suggested_{suggested}"] += 1

    stats["output_rows"] = len(records)
    return records, stats


def balanced_sample(records: Sequence[dict], size: int, seed: int) -> List[dict]:
    rng = random.Random(seed)
    by_label: Dict[str, List[dict]] = defaultdict(list)
    for record in records:
        by_label[record["suggested_label"]].append(record)

    picked: List[dict] = []
    target = max(1, size // max(1, len(by_label)))
    for label in sorted(by_label):
        pool = by_label[label]
        picked.extend(rng.sample(pool, min(target, len(pool))))

    if len(picked) < size:
        picked_ids = {record["id"] for record in picked}
        remaining = [record for record in records if record["id"] not in picked_ids]
        picked.extend(rng.sample(remaining, min(size - len(picked), len(remaining))))

    rng.shuffle(picked)
    return picked[:size]


def write_csv(path: Path, records: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare weak-label web candidate packs.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--pilot-size", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.input.exists():
        raise SystemExit(f"Missing input: {args.input}")

    records, stats = load_candidates(args.input)
    pilot = balanced_sample(records, min(args.pilot_size, len(records)), args.seed)
    all_path = args.out_dir / "en_otp_phishing_10k_all_suggested.csv"
    pilot_path = args.out_dir / "en_otp_phishing_10k_pilot_1000.csv"
    write_csv(all_path, records)
    write_csv(pilot_path, pilot)

    summary = {
        "version": "1.0.0",
        "source": SOURCE_ID,
        "source_license": "MIT (dataset card README)",
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "stats": dict(stats),
        "pilot_rows": len(pilot),
        "pilot_distribution": dict(Counter(r["suggested_label"] for r in pilot)),
        "usage": "human annotation candidate only; not frozen acceptance gold",
        "safety": "sender field intentionally not exported",
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(records)} candidates -> {all_path}")
    print(f"Wrote {len(pilot)} pilot rows -> {pilot_path}")
    print(f"Wrote summary -> {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
