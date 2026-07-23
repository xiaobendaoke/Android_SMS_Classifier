#!/usr/bin/env python3
"""Prepare dual-annotator freeze candidate packs (NOT claimable until both finish).

For each language × trainable label, sample up to --per-class rows from already
labeled interim CSVs, clear label/annotator for fresh dual labeling, and write:

  training/data/interim/annotation/acceptance_packs/freeze/
    freeze_pool.csv                 # master pool with prior_label kept
    freeze_annotator_A.csv          # empty label/annotator
    freeze_annotator_B.csv          # empty label/annotator (same ids)
    freeze_shortfall.json           # cells that cannot reach target
    README_FREEZE_DUAL.txt

Acceptance still requires:
  - both annotators finish independently
  - agreement merge / adjudication
  - freeze SHA recorded before evaluate claim
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.schema import LABEL_ORDER, VALID_LANGUAGES  # noqa: E402

ANN_DIR = ROOT / "data" / "interim" / "annotation"
OUT_DIR = ANN_DIR / "acceptance_packs" / "freeze"

FIELDNAMES = [
    "id",
    "text",
    "language",
    "source",
    "prior_label",
    "suggested_label",
    "suggest_reason",
    "label",
    "annotator",
    "template_group",
    "notes",
    "pack_role",
]

PACKS: List[Tuple[str, str]] = [
    ("zh_all_suggested.csv", "zh"),
    ("uci_all_suggested.csv", "en"),
    ("id_yudiwbs_all_suggested.csv", "id"),
    ("id_spamshield_all_suggested.csv", "id"),
    ("iiitd_all_suggested.csv", "hi"),
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Prepare dual-annotator freeze candidate packs.")
    p.add_argument("--ann-dir", type=Path, default=ANN_DIR)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--per-class", type=int, default=500, help="Freeze target per lang×label.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--annotator-a",
        default="annotator_A",
        help="Placeholder name written into README only (CSV annotator column stays empty).",
    )
    p.add_argument("--annotator-b", default="annotator_B")
    return p


def template_group_of(text: str, rid: str) -> str:
    norm = re.sub(r"\d+", "0", (text or "").lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    if not norm:
        return f"tpl-{rid}"
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


def load_labeled_pool(ann_dir: Path) -> Dict[Tuple[str, str], List[dict]]:
    buckets: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    seen_ids = set()
    for filename, lang_fb in PACKS:
        path = ann_dir / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                rid = (row.get("id") or "").strip()
                text = (row.get("text") or "").strip()
                label = (row.get("label") or "").strip().upper()
                if not rid or not text or label not in LABEL_ORDER:
                    continue
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
                lang = (row.get("language") or lang_fb).strip().lower() or lang_fb
                if lang not in VALID_LANGUAGES:
                    continue
                buckets[(lang, label)].append(
                    {
                        "id": rid,
                        "text": text,
                        "language": lang,
                        "source": (row.get("source") or filename).strip(),
                        "prior_label": label,
                        "suggested_label": label,
                        "suggest_reason": "freeze_resample_from_labeled",
                        "label": "",
                        "annotator": "",
                        "template_group": (row.get("template_group") or "").strip()
                        or template_group_of(text, rid),
                        "notes": "Dual freeze candidate. Re-label independently; ignore prior_label.",
                        "pack_role": "freeze_candidate",
                    }
                )
    return buckets


def sample_freeze(
    buckets: Dict[Tuple[str, str], List[dict]],
    *,
    per_class: int,
    seed: int,
) -> Tuple[List[dict], dict]:
    rng = random.Random(seed)
    picked: List[dict] = []
    shortfall = {}
    for lang in sorted(VALID_LANGUAGES):
        shortfall[lang] = {}
        for label in LABEL_ORDER:
            pool = list(buckets.get((lang, label), []))
            rng.shuffle(pool)
            # Prefer diverse template groups
            by_tpl: Dict[str, List[dict]] = defaultdict(list)
            for row in pool:
                by_tpl[row["template_group"]].append(row)
            ordered: List[dict] = []
            tpl_keys = list(by_tpl.keys())
            rng.shuffle(tpl_keys)
            # round-robin templates
            while any(by_tpl[k] for k in tpl_keys):
                for k in tpl_keys:
                    if by_tpl[k]:
                        ordered.append(by_tpl[k].pop())
            take = ordered[:per_class]
            picked.extend(take)
            shortfall[lang][label] = {
                "have_in_pool": len(pool),
                "sampled": len(take),
                "target": per_class,
                "shortfall": max(0, per_class - len(take)),
            }
    picked.sort(key=lambda r: (r["language"], r["prior_label"], r["id"]))
    return picked, shortfall


def write_csv(path: Path, records: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k, "") for k in FIELDNAMES})


def blank_copy(records: Sequence[dict]) -> List[dict]:
    out = []
    for r in records:
        item = dict(r)
        item["label"] = ""
        item["annotator"] = ""
        out.append(item)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    buckets = load_labeled_pool(args.ann_dir)
    if not buckets:
        print(f"No labeled rows under {args.ann_dir}", file=sys.stderr)
        return 1

    pool, shortfall = sample_freeze(buckets, per_class=args.per_class, seed=args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    pool_path = args.out_dir / "freeze_pool.csv"
    a_path = args.out_dir / "freeze_annotator_A.csv"
    b_path = args.out_dir / "freeze_annotator_B.csv"
    write_csv(pool_path, pool)
    write_csv(a_path, blank_copy(pool))
    write_csv(b_path, blank_copy(pool))

    meta = {
        "version": "1.0.0",
        "per_class_target": args.per_class,
        "seed": args.seed,
        "total_sampled": len(pool),
        "by_lang_label": {
            lang: {lab: shortfall[lang][lab] for lab in LABEL_ORDER}
            for lang in sorted(VALID_LANGUAGES)
        },
        "total_shortfall": sum(
            shortfall[lang][lab]["shortfall"]
            for lang in shortfall
            for lab in shortfall[lang]
        ),
        "annotator_files": {
            args.annotator_a: a_path.name,
            args.annotator_b: b_path.name,
        },
        "claim_note": (
            "Sampling alone does NOT create acceptance gold. "
            "Both annotators must label independently; merge agreements; "
            "record freeze SHA before evaluate claim."
        ),
    }
    short_path = args.out_dir / "freeze_shortfall.json"
    short_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    readme = args.out_dir / "README_FREEZE_DUAL.txt"
    readme.write_text(
        f"""Freeze dual-annotation pack
===========================

Files
-----
- freeze_pool.csv          master list (prior_label = old single-annotator label)
- freeze_annotator_A.csv   for {args.annotator_a} — fill label + annotator only
- freeze_annotator_B.csv   for {args.annotator_b} — fill label + annotator only
- freeze_shortfall.json    cells that could not reach {args.per_class}/class

Rules
-----
1. A and B must NOT look at each other's sheets or at prior_label while labeling.
2. Legal labels: TRANSACTION | AD | HARASS | FRAUD | NEEDS_REVIEW
3. After both finish, merge: same label → candidate gold; conflict → adjudicator.
4. Only agreed (or adjudicated) four-class rows enter the frozen test SHA.
5. Cells with shortfall>0 in freeze_shortfall.json still need NEW source data
   (especially en TRANSACTION, hi FRAUD/TXN, Devanagari hi).

Sampled now: {len(pool)} rows. Remaining shortfall units: {meta['total_shortfall']}.

This pack is a WORK QUEUE for dual annotation — not yet an acceptance freeze.
""",
        encoding="utf-8",
    )

    print(f"Wrote {pool_path} n={len(pool)}")
    print(f"Wrote {a_path}")
    print(f"Wrote {b_path}")
    print(f"Wrote {short_path} total_shortfall={meta['total_shortfall']}")
    print("Per-cell sampled/shortfall:")
    for lang in sorted(VALID_LANGUAGES):
        for lab in LABEL_ORDER:
            cell = shortfall[lang][lab]
            print(
                f"  {lang}/{lab}: sampled={cell['sampled']} "
                f"pool={cell['have_in_pool']} short={cell['shortfall']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
