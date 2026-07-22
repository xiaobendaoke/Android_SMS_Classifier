#!/usr/bin/env python3
"""Quick QA report for annotated UCI four-class CSV."""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

PATH = Path("training/data/interim/annotation/uci_all_suggested.csv")


def norm(x: str) -> str:
    return (x or "").strip().upper()


FRAUD_KW = [
    r"you have won",
    r"you've won",
    r"winner!!",
    r"prize reward",
    r"claim code",
    r"to claim call",
    r"to claim txt",
    r"jackpot",
    r"guaranteed £",
    r"guaranteed \$",
    r"bonus prize",
    r"unredeemed bonus",
    r"account statement.{0,80}claim",
    r"won a guaranteed",
    r"awarded .{0,30}prize",
    r"cash prize",
    r"£900 prize",
    r"£1000 prize",
    r"£2000",
]
TXN_KW = [
    r"transaction id",
    r"account has been refilled",
    r"prepaid account balance",
    r"verification code",
    r"one-time password",
    r"\botp\b",
    r"out for delivery",
    r"tracking number",
    r"booking confirmed",
    r"has been credited",
    r"has been debited",
]
AD_KW = [
    r"ringtone",
    r"subscription",
    r"% off",
    r"discount",
    r"reply stop",
    r"txt stop",
    r"free msg",
    r"freemsg",
    r"will be charged",
    r"std txt rate",
]
HARASS_KW = [
    r"xxx",
    r"sexy",
    r"horny",
    r"get laid",
    r"dogging",
    r"hardcore",
    r"secret admirer",
    r"meet someone sexy",
    r"naked",
]


def hit(text: str, pats: list[str]) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in pats)


def looks_personal(text: str) -> bool:
    t = text.lower()
    if hit(text, FRAUD_KW + TXN_KW + AD_KW + HARASS_KW):
        return False
    return bool(
        re.search(
            r"\b(lol|haha|yeah|okie|meet|later|love you|miss you|dinner|movie|coming)\b",
            t,
        )
    )


def main() -> None:
    rows = list(csv.DictReader(PATH.open(encoding="utf-8-sig")))
    print(f"file={PATH}")
    print(f"total={len(rows)} cols={list(rows[0].keys())}")

    labels = Counter(norm(r["label"]) for r in rows)
    print("label_dist=", dict(labels))
    print(
        "annotator_filled=",
        sum(1 for r in rows if (r.get("annotator") or "").strip()),
    )
    print("notes_filled=", sum(1 for r in rows if (r.get("notes") or "").strip()))

    mx: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        mx[r["uci_binary"]][norm(r["label"])] += 1
    print("by_binary:")
    for b in ("ham", "spam"):
        print(f"  {b}: {dict(mx[b])}")

    flags: dict[str, list] = defaultdict(list)
    for r in rows:
        lab, text, binary = norm(r["label"]), r["text"], r["uci_binary"]
        if hit(text, FRAUD_KW) and lab != "FRAUD":
            flags["fraud_kw_not_FRAUD"].append(r)
        if lab == "FRAUD" and hit(text, HARASS_KW) and not hit(text, FRAUD_KW):
            flags["FRAUD_but_adultish"].append(r)
        if lab == "FRAUD" and hit(text, AD_KW) and not hit(text, FRAUD_KW):
            flags["FRAUD_but_adish"].append(r)
        if lab == "TRANSACTION" and hit(text, FRAUD_KW):
            flags["TXN_but_fraud_kw"].append(r)
        if lab == "TRANSACTION" and binary == "spam" and not hit(text, TXN_KW):
            flags["TXN_on_spam_no_txn_kw"].append(r)
        if (
            lab in {"TRANSACTION", "AD", "HARASS", "FRAUD"}
            and binary == "ham"
            and looks_personal(text)
            and not hit(text, TXN_KW + FRAUD_KW + AD_KW + HARASS_KW)
        ):
            flags["ham_personal_forced_class"].append(r)
        if hit(text, HARASS_KW) and lab not in {"HARASS", "FRAUD", "NEEDS_REVIEW"}:
            flags["adult_kw_not_HARASS"].append(r)
        if lab == "NEEDS_REVIEW" and hit(text, FRAUD_KW):
            flags["REVIEW_but_fraud_kw"].append(r)
        if lab == "NEEDS_REVIEW" and hit(text, TXN_KW) and not hit(text, FRAUD_KW):
            flags["REVIEW_but_txn_kw"].append(r)
        if lab == "AD" and hit(text, FRAUD_KW):
            flags["AD_but_fraud_kw"].append(r)
        if lab == "HARASS" and hit(text, FRAUD_KW):
            flags["HARASS_but_fraud_kw"].append(r)

    print("\nflag_counts:")
    for k, v in sorted(flags.items(), key=lambda x: -len(x[1])):
        print(f"  {k}: {len(v)}")

    # template consistency
    by_tg: dict[str, set] = defaultdict(set)
    for r in rows:
        tg = (r.get("template_group") or "").strip()
        if tg:
            by_tg[tg].add(norm(r["label"]))
    inconsist = [tg for tg, labs in by_tg.items() if len(labs) > 1]
    print(f"\ntemplate_groups={len(by_tg)} multi_label_groups={len(inconsist)}")

    def show(name: str, n: int = 8) -> None:
        items = flags.get(name, [])
        print(f"\n--- {name} ({min(n, len(items))}/{len(items)}) ---")
        for r in items[:n]:
            t = r["text"].replace("\n", " ")[:150]
            print(f"[{r['id']}|{r['uci_binary']}|{norm(r['label'])}] {t}")

    for name in [
        "fraud_kw_not_FRAUD",
        "REVIEW_but_fraud_kw",
        "AD_but_fraud_kw",
        "HARASS_but_fraud_kw",
        "REVIEW_but_txn_kw",
        "TXN_on_spam_no_txn_kw",
        "TXN_but_fraud_kw",
        "FRAUD_but_adultish",
        "FRAUD_but_adish",
        "adult_kw_not_HARASS",
        "ham_personal_forced_class",
    ]:
        if flags.get(name):
            show(name, 10)

    print("\n=== ALL TRANSACTION ===")
    for r in rows:
        if norm(r["label"]) == "TRANSACTION":
            print(f"[{r['id']}|{r['uci_binary']}] {r['text'][:180]}")

    # spam labeled NEEDS_REVIEW rate
    spam = [r for r in rows if r["uci_binary"] == "spam"]
    spam_review = sum(1 for r in spam if norm(r["label"]) == "NEEDS_REVIEW")
    print(f"\nspam_total={len(spam)} spam_as_NEEDS_REVIEW={spam_review} ({spam_review/len(spam):.1%})")
    ham = [r for r in rows if r["uci_binary"] == "ham"]
    ham_four = sum(1 for r in ham if norm(r["label"]) in {"TRANSACTION", "AD", "HARASS", "FRAUD"})
    print(f"ham_total={len(ham)} ham_forced_into_4class={ham_four} ({ham_four/len(ham):.1%})")

    # sample each class
    print("\n=== random-ish samples per class (first 5) ===")
    seen = Counter()
    for r in rows:
        lab = norm(r["label"])
        if seen[lab] >= 5:
            continue
        seen[lab] += 1
        print(f"[{lab}|{r['uci_binary']}] {r['text'][:140]}")


if __name__ == "__main__":
    main()
