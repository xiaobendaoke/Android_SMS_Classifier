#!/usr/bin/env python3
"""Fix iiitd_all_suggested.csv labels to match labeling guide."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

ANN = Path(
    r"C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"
    r"\training\data\interim\annotation"
)
CSV_PATH = ANN / "iiitd_all_suggested.csv"
BACKUP = ANN / "iiitd_all_suggested.bak_before_fixpass.csv"
VALID = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}


def load_rows():
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def is_quiz(low: str) -> bool:
    return bool(
        re.search(
            r"(who (won|do you|is)|which (team|player)|how many|"
            r"can you guess|want to know|want a sample|"
            r"\^1/|\^yes|reply within|option [123]|1\) |2\) |3\))",
            low,
        )
    )


def is_prize_fraud(low: str) -> bool:
    if re.search(
        r"(your number (has )?won|has been awarded|is selected for|"
        r"winner!\s*\d|claim your prize|cash prize|"
        r"\d{3,},\d{3}\s*(gbp|pounds|\$)|"
        r"lottery held|intl draw|coca-?cola.*/?uk|"
        r"hot diamond|yahoo/?msn lottery)",
        low,
    ):
        return True
    if "congratulations" in low or "ongratulations" in low:
        if any(k in low for k in ["won", "claim", "voucher", "pearl set", "lucky winner"]):
            # discount voucher claim against "spl Numero" often scammy
            if any(k in low for k in ["claim", "absolutely free", "pearl", "cash", "gbp", "pounds"]):
                return True
    return False


def is_recharge_promo(low: str) -> bool:
    return bool(
        re.search(
            r"(full talktime|ke recharge|recharge (par|pe|mein|now|with)|"
            r"talktime (validity|ki validity)|best (full )?talktime|"
            r"recharge alert|stvs? to con|"
            r"dial karein \*121|best offer janiye|"
            r"airtel 3g.*(watch|play|games|tv channels)|"
            r"get train details|send and receive money instantly|"
            r"hello tune|football-barclays|"
            r"go to http://m\.google)",
            low,
        )
    )


def is_hard_txn(low: str, t: str) -> bool:
    if "indian railways" in low and "pnr" in low:
        return True
    if any(
        k in low
        for k in [
            "service has been activated",
            "settings have been successfully delivered",
            "mms settings have been successfully",
            "mobile office is active",
            "mobile office & mms is active",
            "please complete registration process",
            "request timed out",
        ]
    ):
        return True
    if re.search(r"\botp\b|verification code|a/c credited|debited|txn id", low):
        return True
    # railway server busy is operational notice
    if "indian railways servers are very busy" in low:
        return True
    return False


def is_adult_harass(low: str) -> bool:
    return any(
        k in low
        for k in ["get laid", "sexy", "call girl", "xxx", "dating service", "adult"]
    )


def is_job_harass(low: str) -> bool:
    return bool(
        re.search(r"(sms sending job|earn rs\.?\s*\d+|work from home).{0,40}(call|www)", low)
    )


def decide(r: dict) -> tuple[str, str] | None:
    """Return (new_label, reason) or None to keep."""
    t = r.get("text") or ""
    low = t.lower()
    L = (r.get("label") or "").strip()
    orig = (r.get("orig_label") or "").strip()

    # --- Strong FRAUD ---
    if is_prize_fraud(low):
        if L != "FRAUD":
            return "FRAUD", "假中奖/彩票认领诈骗"
        return None

    # Quiz / premium content Q&A — not FRAUD
    if is_quiz(low) and not is_prize_fraud(low):
        # adult/dating quiz rare; default AD for subscription/content promo
        # if premium-rate pressure without brand, HARASS also ok; prefer AD for music/sports quiz
        target = "HARASS" if is_adult_harass(low) else "AD"
        if L != target:
            return target, "问答/竞猜增值短信，非诈骗"
        return None

    # Adult / job spam
    if is_adult_harass(low) or is_job_harass(low):
        if L != "HARASS":
            return "HARASS", "成人/灰产兼职骚扰"
        return None

    # Hard TRANSACTION
    if is_hard_txn(low, t):
        if L != "TRANSACTION":
            return "TRANSACTION", "业务结果/系统激活/PNR等事务通知"
        return None

    # Mobile banking receive instructions
    if "receive money through mobile banking" in low or (
        "provide mobile no" in low and "mmid" in low
    ):
        if L != "TRANSACTION":
            return "TRANSACTION", "网银/手机银行收款说明"
        return None

    # Recharge / VAS / marketing currently TXN or FRAUD → AD
    if is_recharge_promo(low) and not is_hard_txn(low, t):
        if L in {"TRANSACTION", "FRAUD", "HARASS", "NEEDS_REVIEW"}:
            return "AD", "充值套餐/增值服务促销"
        return None

    # Open bank account free ATM — AD not FRAUD
    if "open an account with federal bank" in low:
        if L != "AD":
            return "AD", "银行开户促销"
        return None

    # Win trip at dealership / hyundai campaign — promo AD (not classic fraud)
    if "win a hong kong trip" in low and "hyundai" in low:
        if L != "AD":
            return "AD", "车商活动抽奖促销"
        return None

    # "won mobile in last match / dial premium" — premium tease, often AD/HARASS
    if "had won mobile phone" in low or "winning an ipod" in low:
        if "dial" in low and L == "FRAUD":
            return "AD", "增值抽奖拨号促销(非经典转账诈骗)"
        return None

    # Ecovillage free car flat promo — AD/HARASS grey; treat as AD
    if "ecovillage" in low and L == "FRAUD":
        return "AD", "房产促销话术"

    # Fragment google link
    if "http://m.google.co.in" in low and len(t) < 80:
        if L != "NEEDS_REVIEW":
            return "NEEDS_REVIEW", "残缺链接无法判断"
        return None

    # Trip to Thailand / pack ur bag with large WFP amounts — often MLM/fraud
    if any(k in low for k in ["ticket to thailand", "trip to thailand", "pack ur bag"]):
        if any(k in low for k in ["600000", "3lac", "wfp", "qualfiars"]):
            if L != "FRAUD":
                return "FRAUD", "高门槛旅游抽奖/传销式诱导"
            return None

    # ham personal should stay REVIEW unless clear txn
    if orig == "ham" and L not in {"NEEDS_REVIEW", "TRANSACTION", "FRAUD"}:
        # keep AD for rare ham promos
        pass

    # "I M FROM MTS PLZ SEND UR EMAIL" — social engineering / phishing-ish
    if "send ur email id" in low and L != "FRAUD":
        return "FRAUD", "索要邮箱/联系方式可疑"
        # actually could be HARASS; fraud if phishing. Keep FRAUD as labeled.

    return None


def audit(rows):
    issues = Counter()
    for r in rows:
        t = (r.get("text") or "").lower()
        L = (r.get("label") or "").strip()
        if L == "TRANSACTION" and is_recharge_promo(t) and not is_hard_txn(t, r.get("text") or ""):
            issues["TXN_recharge_promo"] += 1
        if L == "FRAUD" and is_quiz(t) and not is_prize_fraud(t):
            issues["FRAUD_quiz"] += 1
        if L == "AD" and is_prize_fraud(t):
            issues["AD_prize_fraud"] += 1
        if L == "AD" and "receive money through mobile banking" in t:
            issues["AD_banking_txn"] += 1
        if not (r.get("annotator") or "").strip():
            issues["empty_annotator"] += 1
    return dict(issues)


def main() -> None:
    if not BACKUP.exists():
        BACKUP.write_bytes(CSV_PATH.read_bytes())

    fields, rows = load_rows()
    applied = []
    for r in rows:
        dec = decide(r)
        if not dec:
            continue
        new, reason = dec
        old = (r.get("label") or "").strip()
        if old == new:
            continue
        r["label"] = new
        note = (r.get("notes") or "").strip()
        fix = f"[fix:{old}->{new}] {reason}"
        r["notes"] = (note + " | " + fix).strip(" |") if note else fix
        if "reason" in r:
            r["reason"] = reason
        applied.append({"id": r["id"], "old": old, "new": new, "reason": reason})

    for r in rows:
        if not (r.get("annotator") or "").strip():
            r["annotator"] = "audit_fixpass_iiitd"

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # second pass: remaining quiz in HARASS that are sports/music → AD
    fields, rows = load_rows()
    extra = []
    for r in rows:
        low = (r.get("text") or "").lower()
        L = (r.get("label") or "").strip()
        if L == "HARASS" and is_quiz(low) and not is_adult_harass(low) and not is_job_harass(low):
            r["label"] = "AD"
            note = (r.get("notes") or "").strip()
            fix = "[fix:HARASS->AD] 体育/娱乐问答增值促销"
            r["notes"] = (note + " | " + fix).strip(" |") if note else fix
            extra.append(r["id"])
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    out = {
        "applied": len(applied),
        "quiz_harass_to_ad": len(extra),
        "label_dist": dict(Counter((r.get("label") or "").strip() for r in rows)),
        "audit_remaining": audit(rows),
        "by_transition": {
            f"{a}->{b}": n
            for (a, b), n in Counter((c["old"], c["new"]) for c in applied).items()
        },
        "changes_sample": applied[:40],
    }
    (ANN / "_iiitd_audit_after_fix.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ANN / "_fix_iiitd.json").write_text(
        json.dumps({"changes": applied + [{"id": i, "old": "HARASS", "new": "AD", "reason": "quiz->AD"} for i in extra]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
