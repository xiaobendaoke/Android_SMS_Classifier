#!/usr/bin/env python3
"""Apply labeling-guide fixes to annotated UCI CSV (in-place with backup)."""
from __future__ import annotations

import csv
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

PATH = Path("training/data/interim/annotation/uci_all_suggested.csv")

ADULT_PAT = re.compile(
    r"\b(xxx|sexy|sex\b|horny|get laid|dogging|hardcore|naked|live sex|"
    r"filthyguys|picsfree|bangbabes|booty|porn|erotic)\b",
    re.I,
)
SECRET_ADMIRER_PAT = re.compile(r"secret admirer", re.I)
CALLERTUNE_PAT = re.compile(r"caller\s*tune|callertune", re.I)

# Clear prize / claim-scam → FRAUD
FRAUD_PAT = re.compile(
    r"("
    r"you have won|you've won|winner!!|prize reward|claim code|"
    r"to claim call|to claim txt|jackpot|bonus prize|bonus caller prize|"
    r"unredeemed bonus|won a guaranteed|cash prize|"
    r"awarded .{0,40}prize|selected to receivea?\s*[£$]|selected to receive a\s*[£$]|"
    r"guaranteed .{0,20}(cash|prize)|complimentary trip|"
    r"account statement.{0,80}(claim|bonus|un-?redeemed)"
    r")",
    re.I | re.S,
)

# Commercial promo that was over-labeled FRAUD → AD
COMMERCIAL_AD_PAT = re.compile(
    r"("
    r"ringtone|discount vouchers?|discount code|voucher holder|"
    r"savamob|subscription|will be charged|free msg|freemsg|"
    r"reply stop|txt stop|stop further messages|"
    r"colour mobiles|mobile update"
    r")",
    re.I,
)

# Personal chat wrongly forced into a class
PERSONAL_FORCE_IDS = {
    "uci_00733",  # Lol steak dinner → was FRAUD
    "uci_02622",  # Lol home chat → was AD
    "uci_03703",  # lover chat → was HARASS (personal intimate, not commercial harass SMS)
}


def norm(x: str) -> str:
    return (x or "").strip().upper()


def decide(row: dict) -> tuple[str | None, str]:
    """Return (new_label or None, reason)."""
    rid = row["id"]
    text = row["text"]
    lab = norm(row["label"])
    binary = (row.get("uci_binary") or "").strip().lower()

    if rid in PERSONAL_FORCE_IDS:
        return "NEEDS_REVIEW", "personal-chat-not-four-class"

    if CALLERTUNE_PAT.search(text):
        if lab != "TRANSACTION":
            return "TRANSACTION", "callertune-service-result"

    # Adult / grey dating / secret admirer → HARASS (spam only; ham "xxx"=kisses)
    if binary == "spam" and (SECRET_ADMIRER_PAT.search(text) or ADULT_PAT.search(text)):
        # Exception: if also clear prize-claim fraud lexicon, FRAUD wins
        if FRAUD_PAT.search(text) and not SECRET_ADMIRER_PAT.search(text):
            if lab != "FRAUD":
                return "FRAUD", "adult-text-but-prize-fraud"
        elif lab != "HARASS":
            return "HARASS", "adult-or-secret-admirer"
    if re.search(r"xxxmobilemovieclub|live sex video", text, re.I) and lab != "HARASS":
        return "HARASS", "adult-brand"

    # Missed / wrong prize fraud
    if FRAUD_PAT.search(text):
        if lab in {"NEEDS_REVIEW", "AD", "HARASS"}:
            return "FRAUD", "prize-claim-fraud"
        return None, ""

    # Over-labeled FRAUD commercial promo → AD
    if lab == "FRAUD" and COMMERCIAL_AD_PAT.search(text) and not FRAUD_PAT.search(text):
        return "AD", "commercial-promo-not-fraud"

    # Ham personal forced: short heuristic for remaining Lol-like wrongly in four-class
    if (
        binary == "ham"
        and lab in {"AD", "FRAUD", "HARASS"}
        and re.search(r"\b(lol|haha|love you|dinner)\b", text, re.I)
        and not FRAUD_PAT.search(text)
        and not ADULT_PAT.search(text)
        and not COMMERCIAL_AD_PAT.search(text)
    ):
        return "NEEDS_REVIEW", "ham-personal-forced"

    return None, ""


def main() -> int:
    if not PATH.exists():
        print(f"missing {PATH}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = PATH.with_suffix(f".bak_{stamp}.csv")
    shutil.copy2(PATH, backup)
    print(f"backup -> {backup}")

    with PATH.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    before = Counter(norm(r["label"]) for r in rows)
    changes: list[tuple[str, str, str, str]] = []

    for r in rows:
        new_lab, reason = decide(r)
        if not new_lab:
            continue
        old = norm(r["label"])
        if old == new_lab:
            continue
        r["label"] = new_lab
        note = (r.get("notes") or "").strip()
        fix_note = f"[fix:{reason} {old}->{new_lab}]"
        r["notes"] = f"{fix_note} {note}".strip() if note else fix_note
        if not (r.get("annotator") or "").strip():
            r["annotator"] = "qa_fix_v1"
        changes.append((r["id"], old, new_lab, reason))

    with PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    after = Counter(norm(r["label"]) for r in rows)
    print(f"changed={len(changes)}")
    print("before=", dict(before))
    print("after =", dict(after))
    by_reason = Counter(c[3] for c in changes)
    print("by_reason=", dict(by_reason))
    print("\nsample changes:")
    for item in changes[:25]:
        print(f"  {item[0]}: {item[1]}->{item[2]} ({item[3]})")
    if len(changes) > 25:
        print(f"  ... +{len(changes)-25} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
