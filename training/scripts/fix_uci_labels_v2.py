#!/usr/bin/env python3
"""Second-pass UCI label fixes (ham forced, spam REVIEW leftovers, promo≠FRAUD)."""
from __future__ import annotations

import csv
import re
import shutil
from collections import Counter
from pathlib import Path

ANN = Path(
    r"C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"
    r"\training\data\interim\annotation"
)
PATH = ANN / "uci_all_suggested.csv"
BACKUP = ANN / "uci_all_suggested.bak_before_fixpass_v2.csv"

ADULT = re.compile(
    r"\b(xxx|sexy|sex\b|horny|get laid|dogging|hardcore|naked|live sex|"
    r"filthyguys|picsfree|bangbabes|booty|porn|erotic|babe|dating|blind date)\b",
    re.I,
)
SECRET = re.compile(r"secret admirer", re.I)
FRAUD = re.compile(
    r"("
    r"you have won|you've won|u have won|winner!!|prize reward|claim code|"
    r"to claim call|to claim txt|to claim,? call|jackpot|bonus prize|bonus caller prize|"
    r"unredeemed bonus|won a guaranteed|cash prize|cash award|"
    r"awarded .{0,40}prize|selected to receivea?\s*[£$€]|selected to receive a\s*[£$€]|"
    r"guaranteed .{0,25}(cash|prize)|complimentary (trip|4\*|holiday)|"
    r"account statement.{0,80}(claim|bonus|un-?redeemed)|"
    r"won £|won \?|won \$|£\d{3,}.{0,30}(prize|award|claim)|"
    r"await collection|awaiting collection|"
    r"tenerife holiday|ibiza holiday|costa del sol|"
    r"final notice to collect|important customer service announcement|"
    r"urgent message waiting|call freephone 0800|"
    r"you have been specially selected|u have been specially selected|"
    r"won the £|won the \?|£1000 prize|£900 prize|£800 prize|£2000 prize|"
    r"claim yr prize"
    r")",
    re.I | re.S,
)
AD = re.compile(
    r"("
    r"ringtone|rbt|caller\s*tune|tones?\b|poly#|mono#|"
    r"subscription|will be charged|unsubscribe|reply stop|txt stop|"
    r"colour mobiles?|mobile update|bluetooth|double mins|"
    r"orange line rental|camera phones? 4 free|free ringtone|"
    r"nokia tone|boltblue|logo 2 ur lover|"
    r"half price|latest motorola|sonyericsson|"
    r"quiz|txt (play|win|action|go) to|"
    r"sms auction|free auction|cinema pass|"
    r"camera phone upgrade|pay & go sim|"
    r"content,? games,? tones|themob>|mobstore|"
    r"call germany for only|1 pence per minute|"
    r"update_now|xmas offer|free bluetooth|"
    r"divorce barbie|hmv bonus|hmv quiz|shopping spree|"
    r"free entry into our|weekly competition|"
    r"valentine.{0,20}quiz"
    r")",
    re.I,
)
HARD_FRAUD = re.compile(
    r"("
    r"to claim (call|txt|your)|claim your|claim code|await collection|"
    r"account statement|bonus points|un-?redeemed|"
    r"£\d{3,}\s*(prize|cash|award)|won a guaranteed|"
    r"complimentary (4\*|trip|holiday).{0,40}(claim|call|await)|"
    r"guaranteed £|prize GUARANTEED|cash await"
    r")",
    re.I | re.S,
)


def decide(row: dict) -> tuple[str | None, str]:
    text = row.get("text") or ""
    lab = (row.get("label") or "").strip().upper()
    binary = (row.get("uci_binary") or "").strip().lower()
    low = text.lower()

    if binary == "ham" and lab in {"AD", "FRAUD", "HARASS"}:
        return "NEEDS_REVIEW", "ham-not-four-class"

    if lab == "FRAUD" and AD.search(text) and not HARD_FRAUD.search(text):
        return "AD", "commercial-promo-not-fraud"
    if lab == "FRAUD" and re.search(
        r"(ringtone|nokia tone|sms auction|cinema pass|camera phone upgrade|"
        r"hmv quiz|quiz wkly|tv quiz|txt nokia to)",
        low,
    ):
        if not re.search(
            r"(account statement|bonus points|£900|£1000 prize GUARANTEED|landline)",
            low,
        ):
            return "AD", "ringtone-quiz-auction-ad"

    if binary == "spam" and lab == "NEEDS_REVIEW":
        if SECRET.search(text) or ADULT.search(text) or re.search(
            r"xxxmobilemovieclub|live sex", low
        ):
            return "HARASS", "spam-adult-dating"
        if HARD_FRAUD.search(text) or FRAUD.search(text):
            if (
                AD.search(text)
                and not HARD_FRAUD.search(text)
                and re.search(r"(ringtone|tone|subscription|unsubscribe|mins|bluetooth)", low)
            ):
                return "AD", "spam-review-to-ad"
            return "FRAUD", "spam-review-to-fraud"
        if AD.search(text) or "barbie" in low:
            return "AD", "spam-review-to-ad"
        return "AD", "spam-review-default-ad"

    if lab == "FRAUD" and binary == "ham":
        return "NEEDS_REVIEW", "ham-fraud-revert"
    return None, ""


def main() -> int:
    if not PATH.exists():
        print(f"missing {PATH}")
        return 1
    if not BACKUP.exists():
        shutil.copy2(PATH, BACKUP)
        print(f"backup -> {BACKUP}")

    with PATH.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    before = Counter((r.get("label") or "").strip() for r in rows)
    changes: list[tuple[str, str, str, str]] = []
    for r in rows:
        new_lab, reason = decide(r)
        if not new_lab:
            continue
        old = (r.get("label") or "").strip().upper()
        if old == new_lab:
            continue
        r["label"] = new_lab
        note = (r.get("notes") or "").strip()
        fix_note = f"[fix_v2:{reason} {old}->{new_lab}]"
        r["notes"] = f"{fix_note} {note}".strip() if note else fix_note
        r["annotator"] = "audit_fixpass_en"
        changes.append((r["id"], old, new_lab, reason))

    with PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    after = Counter((r.get("label") or "").strip() for r in rows)
    print(f"changed={len(changes)}")
    print("before=", dict(before))
    print("after =", dict(after))
    print("by_reason=", dict(Counter(c[3] for c in changes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
