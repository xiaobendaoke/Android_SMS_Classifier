#!/usr/bin/env python3
"""Audit iiitd_all_suggested.csv against labeling guide."""
from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

CSV_PATH = Path(
    r"C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"
    r"\training\data\interim\annotation\iiitd_all_suggested.csv"
)
OUT = CSV_PATH.parent / "_iiitd_audit.json"
VALID = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}

FRAUD_K = [
    "you have won",
    "you've won",
    "claim prize",
    "lottery",
    "jackpot",
    "congratulations you",
    "selected as winner",
    "verify account immediately",
    "account suspended",
    "click here to claim",
    "won a",
    "winner!",
    "cash prize",
    "claim your",
]
TXN_K = [
    "otp",
    "one time password",
    "verification code",
    "a/c credited",
    "account credited",
    "debited",
    "txn id",
    "transaction id",
    "delivered",
    "out for delivery",
    "order confirmed",
    "recharge successful",
]
AD_K = [
    "offer",
    "discount",
    "cashback",
    "recharge now",
    "subscribe",
    "free data",
    "limited period",
    "buy now",
    "apply now",
    "emi",
    "tnc apply",
    "sale",
    "flat ",
    "% off",
]
HARASS_K = [
    "get laid",
    "sexy",
    "adult",
    "dating",
    "call girls",
    "debt recovery",
    "overdue",
    "collection agent",
]


def lab(r: dict) -> str:
    return (r.get("label") or "").strip()


def main() -> None:
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            rows = list(csv.DictReader(CSV_PATH.open(encoding=enc, newline="")))
            print("loaded", enc, len(rows))
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError("decode fail")

    labels = Counter(lab(r) for r in rows)
    anns = Counter((r.get("annotator") or "").strip() for r in rows)
    orig = Counter((r.get("orig_label") or "").strip() for r in rows)
    empty = sum(1 for r in rows if not lab(r))
    invalid = [lab(r) for r in rows if lab(r) and lab(r) not in VALID]

    by_text = defaultdict(set)
    for r in rows:
        by_text[(r.get("text") or "").strip()].add(lab(r))
    conflicts = {t: labs for t, labs in by_text.items() if len(labs) > 1}
    cross = Counter(((r.get("orig_label") or "").strip(), lab(r)) for r in rows)

    # script: any Devanagari?
    dev_n = sum(
        1
        for r in rows
        if any("\u0900" <= c <= "\u097F" for c in (r.get("text") or ""))
    )

    issues = defaultdict(list)
    for r in rows:
        t = r.get("text") or ""
        low = t.lower()
        L = lab(r)
        if L not in VALID:
            continue

        if any(k in low for k in FRAUD_K) or re.search(
            r"(won|winner|claim).{0,20}(prize|cash|£|\$|rs\.?\s*\d)", low
        ):
            if L not in {"FRAUD", "NEEDS_REVIEW"}:
                issues["疑似诈骗未标FRAUD"].append(r)

        if L == "TRANSACTION":
            if any(k in low for k in FRAUD_K) or "claim" in low and "prize" in low:
                issues["TXN却像诈骗"].append(r)
            if any(k in low for k in ["loan offer", "apply now", "flat ", "% off", "sale!"]) and not any(
                k in low for k in TXN_K
            ):
                issues["TXN却像广告"].append(r)
            # personal chat short
            if len(t) < 60 and not any(k in low for k in TXN_K) and not re.search(r"\d{4,}", t):
                if not any(k in low for k in ["otp", "credited", "debited", "delivered", "recharge"]):
                    issues["TXN短句无事务信号"].append(r)

        if L == "AD":
            if any(k in low for k in FRAUD_K) or (
                "won" in low and any(k in low for k in ["prize", "cash", "claim"])
            ):
                issues["AD却像诈骗"].append(r)
            if any(k in low for k in ["get laid", "sexy", "call girl", "xxx"]):
                issues["AD却像骚扰"].append(r)

        if L == "HARASS":
            if any(k in low for k in TXN_K) and re.search(r"\d{4,8}", t):
                issues["HARASS却像OTP"].append(r)
            if any(k in low for k in FRAUD_K):
                issues["HARASS却像诈骗"].append(r)

        if L == "FRAUD":
            # quiz spam often AD
            if re.search(r"(who do you|which|reply within|option)", low) and not any(
                k in low for k in FRAUD_K + ["claim", "won ", "winner"]
            ):
                issues["FRAUD却像问答促销"].append(r)
            if any(k in low for k in TXN_K) and "claim" not in low and "won" not in low:
                if re.search(r"(otp|verification code).{0,10}\d{4,}", low):
                    issues["FRAUD却像普通OTP"].append(r)

        if L == "NEEDS_REVIEW":
            if any(k in low for k in TXN_K) and re.search(r"\d{4,}", t):
                if not any(k in low for k in FRAUD_K):
                    issues["REVIEW却像清晰OTP/事务"].append(r)
            if any(k in low for k in FRAUD_K):
                issues["REVIEW却像诈骗"].append(r)

        # orig spam as TRANSACTION suspicious unless clear txn
        if (r.get("orig_label") or "").strip() == "spam" and L == "TRANSACTION":
            if not any(k in low for k in TXN_K):
                issues["原spam却标事务"].append(r)

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
            "devanagari_rows": dev_n,
            "orig_to_label": {f"{a}->{b}": n for (a, b), n in cross.most_common()},
            "issue_counts": {k: len(v) for k, v in sorted(issues.items(), key=lambda x: -len(x[1]))},
        },
        "_random_per_class": {
            L: [
                {
                    "id": r.get("id"),
                    "orig": r.get("orig_label"),
                    "suggested": r.get("suggested_label"),
                    "text": (r.get("text") or "")[:180],
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
                "text": (r.get("text") or "")[:200],
            }
            for r in v[:12]
        ]
    OUT.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dump["_meta"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
