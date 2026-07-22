#!/usr/bin/env python3
"""Audit id_yudiwbs_all_suggested.csv against labeling guide."""
from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

CSV_PATH = Path(
    r"C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"
    r"\training\data\interim\annotation\id_yudiwbs_all_suggested.csv"
)
OUT = CSV_PATH.parent / "_id_yudiwbs_audit.json"
VALID = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}

FRAUD_K = [
    "hadiah",
    "pemenang",
    "menang",
    "klaim",
    "pin:",
    "kode pin",
    "grandprize",
    "undian",
    "jackpot",
    "rp.175",
    "rp175",
    "milyar",
    "miliar",
    "toyota",
    "mobil",
    "cek di:",
    "bit.ly",
    "blogspot",
]
TXN_K = [
    "otp",
    "kode verifikasi",
    "kode otp",
    "kode rahasia",
    "berhasil ditransfer",
    "pembayaran berhasil",
    "saldo anda",
    "tagihan",
    "resi",
    "kode pengambilan",
]
AD_K = [
    "promo",
    "diskon",
    "spesial",
    "kuota",
    "paket flash",
    "berlangganan",
    "aktifkan",
    "mytelkomsel",
    "voucher",
    "cashback",
    "beli paket",
    "iring",
    "rbt",
]
HARASS_K = [
    "pinjaman",
    "pinjmn",
    "pinjam",
    "utang",
    "hutang",
    "tanpa agunan",
    "dukun",
    "santet",
    "pelet",
    "seks",
    "bokep",
]


def lab(r: dict) -> str:
    return (r.get("label") or "").strip()


def main() -> None:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8-sig", newline="")))
    labels = Counter(lab(r) for r in rows)
    anns = Counter((r.get("annotator") or "").strip() for r in rows)
    orig = Counter((r.get("orig_label") or "").strip() for r in rows)
    empty = sum(1 for r in rows if not lab(r))
    invalid = [lab(r) for r in rows if lab(r) and lab(r) not in VALID]

    # same text conflict
    by_text = defaultdict(set)
    for r in rows:
        by_text[(r.get("text") or "").strip()].add(lab(r))
    conflicts = {t: labs for t, labs in by_text.items() if len(labs) > 1}

    # orig vs human
    cross = Counter(((r.get("orig_label") or "").strip(), lab(r)) for r in rows)

    issues = defaultdict(list)
    for r in rows:
        t = (r.get("text") or "")
        low = t.lower()
        L = lab(r)
        if L not in VALID:
            continue

        # clear prize fraud labeled not FRAUD
        if any(k in low for k in ["pemenang", "hadiah ke-", "grandprize", "cek pin"]) or (
            "hadiah" in low and any(k in low for k in ["klik", "pin", "bit.ly", "blogspot", "info hadiah"])
        ):
            if L not in {"FRAUD", "NEEDS_REVIEW"} and "telkomsel" not in low:
                # carrier promo with hadiah may be AD
                if L != "AD" or any(k in low for k in ["blogspot", "bit.ly", "pin pemenang", "toyota", "rp.175"]):
                    if L != "FRAUD":
                        issues["疑似假中奖未标FRAUD"].append(r)

        if L == "TRANSACTION":
            if any(k in low for k in ["hadiah", "pemenang", "pin pemenang", "blogspot"]):
                issues["TXN却像诈骗中奖"].append(r)
            if any(k in low for k in ["pinjaman", "tanpa agunan", "bunga"]) and "otp" not in low:
                issues["TXN却像贷款骚扰"].append(r)
            if any(k in low for k in AD_K) and not any(k in low for k in TXN_K):
                # promo without txn signal
                if any(k in low for k in ["aktifkan", "promo", "diskon", "beli paket"]):
                    issues["TXN却像广告促销"].append(r)

        if L == "AD":
            if any(k in low for k in ["pemenang", "pin:", "blogspot", "grandprize"]) or (
                "hadiah" in low and any(k in low for k in ["toyota", "rp.", "mobil"])
            ):
                issues["AD却像假中奖诈骗"].append(r)
            if any(k in low for k in ["pinjaman", "tanpa agunan", "bunga %", "bunga%"]) and re.search(
                r"08\d{8,}", t
            ):
                issues["AD却像灰产贷款"].append(r)

        if L == "HARASS":
            if any(k in low for k in TXN_K) and re.search(r"\d{4,8}", t) and "pinjaman" not in low:
                issues["HARASS却像OTP事务"].append(r)
            if any(k in low for k in ["pemenang", "hadiah"]) and any(
                k in low for k in ["pin", "klik", "blogspot"]
            ):
                issues["HARASS却像假中奖"].append(r)

        if L == "FRAUD":
            # clear telco promo without scam claim
            if any(k in low for k in ["mytelkomsel", "paket flash", "kuota"]) and not any(
                k in low for k in ["pemenang", "pin:", "blogspot", "toyota", "klaim"]
            ):
                issues["FRAUD却像运营商广告"].append(r)
            if any(k in low for k in ["otp", "kode verifikasi"]) and not any(
                k in low for k in ["jangan berikan", "kirimkan otp", "minta otp"]
            ):
                if re.search(r"(kode|otp).{0,10}\d{4,8}", low) and "hadiah" not in low:
                    issues["FRAUD却像普通OTP"].append(r)

        if L == "NEEDS_REVIEW":
            if any(k in low for k in ["otp", "kode verifikasi"]) and re.search(r"\d{4,8}", t):
                if not any(k in low for k in ["hadiah", "pemenang"]):
                    issues["REVIEW却像清晰OTP"].append(r)
            if any(k in low for k in ["pemenang", "pin pemenang", "grandprize"]):
                issues["REVIEW却像假中奖"].append(r)

        # orig=1 fraud should often be FRAUD/HARASS/AD not TXN
        if (r.get("orig_label") or "").strip() == "1" and L == "TRANSACTION":
            issues["原标诈骗却标成事务"].append(r)

    rng = random.Random(42)
    by = defaultdict(list)
    for r in rows:
        if lab(r) in VALID:
            by[lab(r)].append(r)

    dump = {
        "_meta": {
            "total": len(rows),
            "fields": list(rows[0].keys()) if rows else [],
            "label_dist": dict(labels),
            "annotator_dist": dict(anns),
            "orig_dist": dict(orig),
            "empty_label": empty,
            "invalid": invalid[:20],
            "unique_texts": len(by_text),
            "label_conflicts": len(conflicts),
            "orig_to_label": {f"{a}->{b}": n for (a, b), n in cross.most_common()},
            "issue_counts": {k: len(v) for k, v in sorted(issues.items(), key=lambda x: -len(x[1]))},
        },
        "_random_per_class": {
            L: [
                {
                    "id": r.get("id"),
                    "orig": r.get("orig_label"),
                    "suggested": r.get("suggested_label"),
                    "text": (r.get("text") or "")[:160],
                }
                for r in rng.sample(lst, min(10, len(lst)))
            ]
            for L, lst in by.items()
        },
    }
    for k, v in issues.items():
        dump[k] = [
            {
                "id": r.get("id"),
                "label": lab(r),
                "orig": r.get("orig_label"),
                "suggested": r.get("suggested_label"),
                "annotator": r.get("annotator"),
                "text": (r.get("text") or "")[:180],
            }
            for r in v[:15]
        ]

    OUT.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dump["_meta"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
