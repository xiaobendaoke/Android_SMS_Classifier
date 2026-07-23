#!/usr/bin/env python3
"""Build HARASS + Indonesian gap re-label packs from interim annotation CSVs.

Pulls from NEEDS_REVIEW (and optional AD→HARASS borderline) rows that are not
yet in the trainable four-class pool for weak cells.

Outputs under training/data/interim/annotation/acceptance_packs/:
  harass_relabel_candidates.csv
  id_gap_fill_candidates.csv
  README_HARASS_ID_RELABEL.txt

Human fills: label + annotator (leave prior_label as-is for audit).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
ANN_DIR = ROOT / "data" / "interim" / "annotation"
OUT_DIR = ANN_DIR / "acceptance_packs"

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

# Weak cells to prioritize for id gap fill (freeze target 500).
ID_PRIORITY_LABELS = ("HARASS", "TRANSACTION", "FRAUD", "AD")

HARASS_HINTS = [
    # zh
    r"催收|欠款|逾期|讨债|灰产|发票代开|色情|约炮|加微信下款|无抵押|赌博|博彩|私服",
    # en
    r"\bdebt\b|\bcollect(ion|or)\b|\boverdue\b|\bloan\b.{0,20}\b(whatsapp|wechat|telegram)\b",
    r"\bsexy\b|\bhook ?up\b|\bget laid\b|\badult\b|\bpoker\b|\bcasino\b",
    # id
    r"hutang|penagihan|terlambat|pinjaman|togel|judi|dewasa|seks",
    # hi / hinglish
    r"loan|debt|collection|sexy|casino|gambling",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Prepare HARASS / id re-label candidate packs.")
    p.add_argument("--ann-dir", type=Path, default=ANN_DIR)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--harass-max", type=int, default=800, help="Max HARASS-candidate rows.")
    p.add_argument("--id-max", type=int, default=1000, help="Max id gap-fill rows.")
    p.add_argument(
        "--include-ad-borderline",
        action="store_true",
        default=True,
        help="Also sample AD rows that match HARASS hints for re-check.",
    )
    p.add_argument("--no-include-ad-borderline", action="store_false", dest="include_ad_borderline")
    return p


def template_group_of(text: str, rid: str) -> str:
    norm = re.sub(r"\d+", "0", (text or "").lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    if not norm:
        return f"tpl-{rid}"
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


def harass_score(text: str) -> Tuple[int, str]:
    t = text or ""
    hits = []
    for pat in HARASS_HINTS:
        if re.search(pat, t, flags=re.IGNORECASE):
            hits.append(pat[:40])
    return len(hits), ";".join(hits[:3])


def read_pack_rows(ann_dir: Path) -> List[dict]:
    rows: List[dict] = []
    for filename, lang_fb in PACKS:
        path = ann_dir / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                rid = (row.get("id") or "").strip()
                text = (row.get("text") or "").strip()
                if not rid or not text:
                    continue
                lang = (row.get("language") or lang_fb).strip().lower() or lang_fb
                prior = (row.get("label") or "").strip().upper()
                rows.append(
                    {
                        "id": rid,
                        "text": text,
                        "language": lang,
                        "source": (row.get("source") or filename).strip(),
                        "prior_label": prior,
                        "template_group": (row.get("template_group") or "").strip()
                        or template_group_of(text, rid),
                        "_file": filename,
                    }
                )
    return rows


def write_csv(path: Path, records: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k, "") for k in FIELDNAMES})


def pick_harass_candidates(rows: List[dict], *, max_n: int, include_ad: bool, seed: int) -> List[dict]:
    rng = random.Random(seed)
    scored: List[Tuple[int, dict]] = []
    for row in rows:
        prior = row["prior_label"]
        score, reason = harass_score(row["text"])
        if prior == "NEEDS_REVIEW" and score > 0:
            item = dict(row)
            item.update(
                {
                    "suggested_label": "HARASS",
                    "suggest_reason": f"nr_hint:{reason}",
                    "label": "",
                    "annotator": "",
                    "notes": "Re-label from NEEDS_REVIEW; prefer HARASS vs AD vs FRAUD.",
                    "pack_role": "harass_relabel",
                }
            )
            scored.append((score + 10, item))
        elif include_ad and prior == "AD" and score > 0:
            item = dict(row)
            item.update(
                {
                    "suggested_label": "HARASS",
                    "suggest_reason": f"ad_borderline:{reason}",
                    "label": "",
                    "annotator": "",
                    "notes": "Was AD — check if HARASS (催收/灰产/成人) or keep AD.",
                    "pack_role": "harass_relabel",
                }
            )
            scored.append((score, item))
        elif prior == "NEEDS_REVIEW" and row["language"] in {"zh", "en", "id", "hi"}:
            # low-priority NR padding so pack is large enough to work through
            item = dict(row)
            item.update(
                {
                    "suggested_label": "NEEDS_REVIEW",
                    "suggest_reason": "nr_pool",
                    "label": "",
                    "annotator": "",
                    "notes": "Open NR — mark HARASS if 扰民非骗转账.",
                    "pack_role": "harass_relabel",
                }
            )
            scored.append((0, item))

    # Prefer higher scores; shuffle within same score
    by_score: Dict[int, List[dict]] = defaultdict(list)
    for s, item in scored:
        by_score[s].append(item)
    ordered: List[dict] = []
    for s in sorted(by_score.keys(), reverse=True):
        bucket = by_score[s]
        rng.shuffle(bucket)
        ordered.extend(bucket)

    # Dedup by id, keep first
    seen = set()
    picked: List[dict] = []
    for item in ordered:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        picked.append(item)
        if len(picked) >= max_n:
            break
    return picked


def pick_id_gap_candidates(rows: List[dict], *, max_n: int, seed: int) -> List[dict]:
    rng = random.Random(seed + 7)
    id_rows = [r for r in rows if r["language"] == "id" and r["prior_label"] == "NEEDS_REVIEW"]
    rng.shuffle(id_rows)

    # Light suggest for id NR using keywords
    txn_re = re.compile(
        r"otp|kode verifikasi|kode rahasia|transfer berhasil|pembayaran berhasil|"
        r"saldo|rekening|resi|pengiriman|pesanan",
        re.I,
    )
    fraud_re = re.compile(
        r"hadiah|menang|undian|pinjaman cair|biaya admin|klik link|akun terblokir",
        re.I,
    )
    harass_re = re.compile(r"hutang|penagihan|terlambat|judi|togel|dewasa", re.I)
    ad_re = re.compile(r"diskon|promo|gratis|beli sekarang|sale|voucher", re.I)

    picked: List[dict] = []
    for row in id_rows:
        text = row["text"]
        if fraud_re.search(text):
            sug, reason = "FRAUD", "id_fraud_hint"
        elif txn_re.search(text):
            sug, reason = "TRANSACTION", "id_txn_hint"
        elif harass_re.search(text):
            sug, reason = "HARASS", "id_harass_hint"
        elif ad_re.search(text):
            sug, reason = "AD", "id_ad_hint"
        else:
            sug, reason = "NEEDS_REVIEW", "id_nr_open"
        # Prefer filling weak labels first by putting hinted rows earlier
        priority = {
            "HARASS": 0,
            "TRANSACTION": 1,
            "FRAUD": 2,
            "AD": 3,
            "NEEDS_REVIEW": 4,
        }[sug]
        item = dict(row)
        item.update(
            {
                "suggested_label": sug,
                "suggest_reason": reason,
                "label": "",
                "annotator": "",
                "notes": "ID gap fill from NEEDS_REVIEW. Fill label; keep NEEDS_REVIEW if unsure.",
                "pack_role": "id_gap_fill",
                "_priority": priority,
            }
        )
        picked.append(item)

    picked.sort(key=lambda r: (r["_priority"], r["id"]))
    out = []
    for item in picked[:max_n]:
        item.pop("_priority", None)
        out.append(item)
    return out


def write_readme(path: Path, harass_n: int, id_n: int, harass_dist: Counter, id_sug: Counter) -> None:
    path.write_text(
        f"""HARASS / Indonesian gap re-label packs
=====================================

Files
-----
- harass_relabel_candidates.csv  ({harass_n} rows)
- id_gap_fill_candidates.csv     ({id_n} rows)

How to annotate
---------------
1. Only fill columns: label, annotator, notes (optional).
2. Legal labels: TRANSACTION | AD | HARASS | FRAUD | NEEDS_REVIEW
3. HARASS = 扰民但不靠骗转账（催收/灰产招揽/成人/硬推销贷款等）
4. If unsure → NEEDS_REVIEW (do not force).
5. Do NOT peek at another annotator's sheet if dual-labeling.

Suggested distributions (hints only)
------------------------------------
harass pack prior/suggested mix: {dict(harass_dist)}
id pack suggested_label mix: {dict(id_sug)}

After labeling
--------------
Merge filled labels back into the corresponding *_all_suggested.csv
(or ask the agent to run a merge helper), then:

  PYTHONPATH=training python training/scripts/convert_annotation_csv_to_jsonl.py
  make prepare-annotation-bootstrap

These packs are engineering refill — NOT the frozen dual-gold set.
""",
        encoding="utf-8",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    rows = read_pack_rows(args.ann_dir)
    if not rows:
        print(f"No interim CSVs under {args.ann_dir}", file=sys.stderr)
        return 1

    harass = pick_harass_candidates(
        rows,
        max_n=args.harass_max,
        include_ad=args.include_ad_borderline,
        seed=args.seed,
    )
    id_pack = pick_id_gap_candidates(rows, max_n=args.id_max, seed=args.seed)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    harass_path = args.out_dir / "harass_relabel_candidates.csv"
    id_path = args.out_dir / "id_gap_fill_candidates.csv"
    write_csv(harass_path, harass)
    write_csv(id_path, id_pack)

    harass_dist = Counter(f"{r['prior_label']}->{r['suggested_label']}" for r in harass)
    id_sug = Counter(r["suggested_label"] for r in id_pack)
    write_readme(
        args.out_dir / "README_HARASS_ID_RELABEL.txt",
        len(harass),
        len(id_pack),
        harass_dist,
        id_sug,
    )

    print(f"Wrote {harass_path} n={len(harass)}")
    print(f"Wrote {id_path} n={len(id_pack)}")
    print("harass prior->suggested:", dict(Counter(f"{r['prior_label']}->{r['suggested_label']}" for r in harass)))
    print("id suggested:", dict(id_sug))
    print(f"langs harass:", dict(Counter(r["language"] for r in harass)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
