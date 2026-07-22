#!/usr/bin/env python3
"""Heuristic recheck of four-language annotation CSVs."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ANN = Path(
    r"C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"
    r"\training\data\interim\annotation"
)
VALID = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}
DEVA = re.compile(r"[\u0900-\u097F]")
CJK = re.compile(r"[\u4e00-\u9fff]")

PRIZE_FRAUD = re.compile(
    r"(claim (your |ur )?(prize|award)|to claim (call|txt)|your number (has )?won|"
    r"has been awarded|lottery held|prize GUARANTEED|"
    r"account statement.{0,60}(claim|bonus|un-?redeemed)|"
    r"恭喜.{0,10}中奖|领奖|klaim hadiah|anda telah memenangkan|pin pemenang|"
    r"£\d{3,}.{0,20}(prize|award|claim)|won £|won \?)",
    re.I | re.S,
)
OTP = re.compile(
    r"(otp|verification code|验证码|kode (otp|verifikasi)|one[- ]time (password|code))",
    re.I,
)
PROMO = re.compile(
    r"(unsubscribe|reply stop|退订|promo|diskon|discount|offer|recharge pack|"
    r"full talktime|ringtone|套餐升级|限时优惠|buruan)",
    re.I,
)
ADULT = re.compile(r"\b(sexy|sex\b|xxx|horny|get laid|porn|bokep|约炮|成人)\b", re.I)
RINGTONE_AD = re.compile(
    r"(ringtone|nokia tone|poly#|tones? for|caller\s*tune subscription)",
    re.I,
)

PACKS = [
    ("zh", "zh_all_suggested.csv", "zh", None),
    ("en", "uci_all_suggested.csv", "en", "uci_binary"),
    ("id_yudi", "id_yudiwbs_all_suggested.csv", "id", "orig_label"),
    ("id_ss", "id_spamshield_all_suggested.csv", "id", "orig_label"),
    ("hi", "iiitd_all_suggested.csv", "hi", "orig_label"),
]

CRITICAL_KEYS = {
    "invalid_or_empty",
    "empty_text",
    "AD_looks_prize_fraud",
    "nonTXN_looks_otp",
    "TXN_looks_fraud",
    "FRAUD_looks_ringtone_ad",
    "ham_forced_fourclass",
}


def main() -> int:
    report: dict = {}
    for key, fname, lang, binary_col in PACKS:
        path = ANN / fname
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))

        labels = Counter((r.get("label") or "").strip() for r in rows)
        annot = Counter((r.get("annotator") or "").strip() or "(empty)" for r in rows)
        issues: Counter = Counter()
        samples: dict = defaultdict(list)

        def add(iss: str, r: dict, limit: int = 8) -> None:
            issues[iss] += 1
            if len(samples[iss]) < limit:
                samples[iss].append(
                    {
                        "id": r.get("id"),
                        "label": r.get("label"),
                        "binary": r.get(binary_col) if binary_col else None,
                        "text": (r.get("text") or "")[:140].replace("\n", " "),
                    }
                )

        for r in rows:
            t = r.get("text") or ""
            low = t.lower()
            lab = (r.get("label") or "").strip()
            binary = (
                (r.get(binary_col) or "").strip().lower() if binary_col else ""
            )

            if lab not in VALID:
                add("invalid_or_empty", r)
                continue
            if not t.strip():
                add("empty_text", r)

            if lab == "AD" and PRIZE_FRAUD.search(t):
                if not re.search(r"(抵用券|优惠代码|大众点评)", t):
                    add("AD_looks_prize_fraud", r)

            if lab in {"AD", "HARASS"} and OTP.search(t) and not PROMO.search(t):
                add("nonTXN_looks_otp", r)

            if lab == "TRANSACTION":
                if re.search(
                    r"(unsubscribe|reply stop|ringtone order|"
                    r"bonus pulsa.{0,20}isi ulang|cuma dgn isi ulang)",
                    low,
                ):
                    add("TXN_looks_hard_promo", r)
                if lang == "zh" and re.search(r"(恭喜中奖|点链接领|验证码发给)", t):
                    add("TXN_looks_fraud", r)
                if lang == "en" and PRIZE_FRAUD.search(t):
                    add("TXN_looks_fraud", r)

            if lab == "FRAUD" and RINGTONE_AD.search(t) and not PRIZE_FRAUD.search(t):
                add("FRAUD_looks_ringtone_ad", r)

            if lab == "AD" and ADULT.search(t) and not PROMO.search(t):
                add("AD_looks_adult_harass", r)

            if binary_col and binary in {"ham", "0", "legit"} and lab in {
                "AD",
                "FRAUD",
                "HARASS",
            }:
                if not (
                    PRIZE_FRAUD.search(t)
                    or RINGTONE_AD.search(t)
                    or ADULT.search(t)
                ):
                    if len(t) < 200:
                        add("ham_forced_fourclass", r)

            if binary_col and binary in {"spam", "1"} and lab == "NEEDS_REVIEW":
                if (
                    PRIZE_FRAUD.search(t)
                    or RINGTONE_AD.search(t)
                    or ADULT.search(t)
                    or PROMO.search(t)
                ):
                    add("spam_review_should_label", r)

            if lang == "zh" and len(t) > 30 and not CJK.search(t):
                add("zh_missing_cjk", r)

        critical = sum(issues[k] for k in issues if k in CRITICAL_KEYS)
        warn = sum(issues[k] for k in issues if k not in CRITICAL_KEYS)
        empty = labels.get("", 0)
        if empty or critical:
            verdict = "FAIL"
        elif warn:
            verdict = "WARN"
        else:
            verdict = "PASS"

        report[key] = {
            "file": fname,
            "n": len(rows),
            "label_dist": dict(labels),
            "annotator_top": dict(annot.most_common(5)),
            "n_devanagari": sum(1 for r in rows if DEVA.search(r.get("text") or "")),
            "n_cjk": sum(1 for r in rows if CJK.search(r.get("text") or "")),
            "critical_count": critical,
            "warn_count": warn,
            "issues": dict(issues),
            "samples": dict(samples),
            "verdict": verdict,
        }

    out = ANN / "_four_lang_recheck.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for key, v in report.items():
        print("=" * 60)
        print(
            f"{key}: verdict={v['verdict']} n={v['n']} "
            f"critical={v['critical_count']} warn={v['warn_count']}"
        )
        print("dist:", v["label_dist"])
        print("issues:", v["issues"] or "{}")
        for iss, items in v["samples"].items():
            print(f"  [{iss}]")
            for it in items[:5]:
                print(
                    f"    - {it['id']} ({it['label']}/{it['binary']}): {it['text']}"
                )
    print("=" * 60)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
