#!/usr/bin/env python3
"""Convert interim four-class annotation CSVs → raw SmsRecord JSONL.

Excludes NEEDS_REVIEW (and empty/invalid labels). Output is homework bootstrap
only — NOT frozen acceptance gold.

Default inputs (under training/data/interim/annotation/):
  zh_all_suggested.csv
  uci_all_suggested.csv
  id_yudiwbs_all_suggested.csv
  id_spamshield_all_suggested.csv
  iiitd_all_suggested.csv
  en_otp_phishing_10k_all_suggested.csv

Default output:
  training/data/raw/annotated_homework_bootstrap.jsonl
  training/data/manifests/annotated_bootstrap_summary.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
ANN_DIR = ROOT / "data" / "interim" / "annotation"
DEFAULT_OUT = ROOT / "data" / "raw" / "annotated_homework_bootstrap.jsonl"
DEFAULT_SUMMARY = ROOT / "data" / "manifests" / "annotated_bootstrap_summary.json"

sys.path.insert(0, str(ROOT))
from src.schema import LABEL_ORDER, SmsRecord, write_jsonl  # noqa: E402

# Pack definitions: (filename, language_fallback, source_fallback, license)
PACKS: List[Tuple[str, str, str, str]] = [
    (
        "zh_all_suggested.csv",
        "zh",
        "gitcode_zh_sms_8a104",
        "CC BY-NC-SA 4.0",
    ),
    (
        "uci_all_suggested.csv",
        "en",
        "uci_sms_spam_collection_v1",
        "UCI research redistribution per dataset readme",
    ),
    (
        "id_yudiwbs_all_suggested.csv",
        "id",
        "yudiwbs_id_sms_spam_v1",
        "CC BY-SA 4.0",
    ),
    (
        "id_spamshield_all_suggested.csv",
        "id",
        "spamshield_indonesian_v1",
        "CC BY 4.0",
    ),
    (
        "iiitd_all_suggested.csv",
        "hi",
        "iiitd_sms_spam_v1",
        "Academic use per IIIT-D Precog distribution",
    ),
    (
        "en_otp_phishing_10k_all_suggested.csv",
        "en",
        "hf_sms_otp_phishing_10k",
        "MIT (dataset card README)",
    ),
]

TRAINABLE = set(LABEL_ORDER)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert annotation CSVs to raw SmsRecord JSONL (drop NEEDS_REVIEW)."
    )
    parser.add_argument(
        "--ann-dir",
        type=Path,
        default=ANN_DIR,
        help="Directory containing *_all_suggested.csv packs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT,
        help="Output JSONL path under data/raw/.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=DEFAULT_SUMMARY,
        help="Summary JSON path.",
    )
    return parser


def _annotator_ids(raw: str) -> List[str]:
    name = (raw or "").strip()
    if not name:
        return ["annotation_csv"]
    return [name]


def row_to_record(
    row: Dict[str, str],
    *,
    language_fallback: str,
    source_fallback: str,
    source_license: str,
) -> Optional[SmsRecord]:
    label = (row.get("label") or "").strip().upper()
    if label not in TRAINABLE:
        return None
    text = (row.get("text") or "").strip()
    if not text:
        return None
    rid = (row.get("id") or "").strip()
    if not rid:
        return None

    language = (row.get("language") or language_fallback).strip().lower() or language_fallback
    source = (row.get("source") or source_fallback).strip() or source_fallback
    template = (row.get("template_group") or "").strip() or f"tpl-{rid}"
    # Per-id sender group keeps group-split from collapsing unrelated SMS.
    sender = f"snd-ann-{rid}"

    return SmsRecord(
        id=rid,
        text=text,
        label=label,
        language=language,
        source=source,
        source_license=source_license,
        sender_group=sender,
        template_group=template,
        split="train",  # reassigned by build_dataset.split_groups
        is_synthetic=False,
        is_adversarial=False,
        parent_id=None,
        annotator_ids=_annotator_ids(row.get("annotator") or ""),
    )


def convert_pack(
    path: Path,
    *,
    language_fallback: str,
    source_fallback: str,
    source_license: str,
) -> Tuple[List[SmsRecord], Counter, int]:
    skipped = 0
    by_label: Counter = Counter()
    records: List[SmsRecord] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rec = row_to_record(
                row,
                language_fallback=language_fallback,
                source_fallback=source_fallback,
                source_license=source_license,
            )
            if rec is None:
                skipped += 1
                continue
            records.append(rec)
            by_label[rec.label] += 1
    return records, by_label, skipped


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if not args.ann_dir.exists():
        print(f"Annotation dir missing: {args.ann_dir}", file=sys.stderr)
        return 1

    all_records: List[SmsRecord] = []
    pack_stats = []
    seen_ids: set[str] = set()
    dupes = 0

    for fname, lang, source, license_name in PACKS:
        path = args.ann_dir / fname
        if not path.exists():
            print(f"WARN: skip missing pack {path}", file=sys.stderr)
            pack_stats.append({"file": fname, "missing": True})
            continue
        records, by_label, skipped = convert_pack(
            path,
            language_fallback=lang,
            source_fallback=source,
            source_license=license_name,
        )
        kept = []
        for rec in records:
            if rec.id in seen_ids:
                dupes += 1
                continue
            seen_ids.add(rec.id)
            kept.append(rec)
        all_records.extend(kept)
        pack_stats.append(
            {
                "file": fname,
                "language": lang,
                "source": source,
                "kept": len(kept),
                "skipped_non_trainable": skipped,
                "label_dist": dict(by_label),
            }
        )
        print(
            f"{fname}: kept={len(kept)} skipped={skipped} labels={dict(by_label)}"
        )

    by_lang_label: Dict[str, Counter] = {}
    for rec in all_records:
        by_lang_label.setdefault(rec.language, Counter())[rec.label] += 1

    write_jsonl(args.output, all_records)
    try:
        out_rel = str(args.output.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        out_rel = str(args.output)
    summary = {
        "version": "1.0.0",
        "note": (
            "Homework bootstrap from audited annotation CSVs. "
            "NEEDS_REVIEW excluded. NOT frozen acceptance gold. "
            "iiitd language=hi is Hinglish/en-IN (not Devanagari)."
        ),
        "output": out_rel,
        "n_records": len(all_records),
        "duplicate_ids_dropped": dupes,
        "label_dist": dict(Counter(r.label for r in all_records)),
        "language_label_dist": {
            lang: dict(counts) for lang, counts in sorted(by_lang_label.items())
        },
        "packs": pack_stats,
        "excluded_labels": ["NEEDS_REVIEW"],
        "usage": "merge with synthetic raw/*.jsonl via build_dataset.py; engineering/homework only",
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(all_records)} records → {args.output}")
    print(f"Wrote summary → {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
