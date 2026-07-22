#!/usr/bin/env python3
"""Fix id_yudiwbs_all_suggested.csv labels to match labeling guide."""
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
CSV_PATH = ANN / "id_yudiwbs_all_suggested.csv"
BACKUP = ANN / "id_yudiwbs_all_suggested.bak_before_fixpass.csv"
VALID = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}


def load_rows():
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def rule_fixes(rows: list[dict]) -> list[dict]:
    changes = []

    def add(r, new, reason):
        old = (r.get("label") or "").strip()
        if old == new or new not in VALID:
            return
        changes.append(
            {"id": r["id"], "old": old, "new": new, "reason": reason, "source": "rules"}
        )

    for r in rows:
        t = r.get("text") or ""
        low = t.lower()
        L = (r.get("label") or "").strip()
        orig = (r.get("orig_label") or "").strip()

        # --- FRAUD: fake prize / claim PIN / phishing ---
        prize_scam = any(
            k in low
            for k in [
                "pemenang",
                "pin pemenang",
                "pin:",
                "kode pin",
                "grandprize",
                "gebyar",
                "toyota",
                "all new yaris",
                "blogspot",
                "undian bri",
                "cek di: bit.ly",
            ]
        ) or (
            "hadiah" in low
            and any(k in low for k in ["mobil", "rp.175", "rp175", "milyar", "klaim", "info hadiah"])
        )
        bank_ask = bool(
            re.search(r"(rek|rekening|transfer).{0,40}(bri|bca|mandiri|bni)", low)
        ) and any(k in low for k in ["kirim", "transfer", "uang"])
        ask_pulsa = bool(re.search(r"(isi\s*(dl\s*)?pulsa|krim plsa|kirim pulsa)", low))

        if prize_scam or bank_ask or (
            ask_pulsa and any(k in low for k in ["08", "rek", "rekening"])
        ):
            # exclude legitimate carrier undian with clear brand and no fake pin claim site
            legit_undian = any(
                k in low for k in ["indosat", "telkomsel", "xl axiata", "tri "]
            ) and ("poin" in low or "kupon" in low) and not any(
                k in low for k in ["blogspot", "pin:", "toyota", "yaris", "pin pemenang"]
            )
            if not legit_undian:
                add(r, "FRAUD", "假中奖/要转账/要充值诈骗")

        # --- Grey phone shops: ultra cheap + personal number ---
        phone_shop = any(
            k in low
            for k in [
                "blackberry",
                "bb dakota",
                "bb onyx",
                "bb torch",
                "bb gemini",
                "bb z10",
                "iphone",
                "samsung",
                "laptop",
            ]
        )
        personal = bool(re.search(r"08\d{8,}", t)) or "pin bb" in low
        cheap = any(
            k in low
            for k in ["disc", "diskon", "discon", "promo", "big sale", "jt", "rb", "murah"]
        )
        brand_telco = any(
            k in low
            for k in ["telkomsel", "indosat", "mytelkomsel", "axis", "xl ", "[xl]"]
        )
        if phone_shop and personal and cheap and not brand_telco:
            add(r, "FRAUD", "私人号超低价电子产品灰产/疑似诈骗店")

        # --- HARASS: loan / togel / dukun ---
        loan = any(
            k in low
            for k in [
                "pinjaman",
                "pinjmn",
                "dana tunai",
                "kta",
                "tanpa agunan",
                "bpkb",
                "bunga",
            ]
        ) and personal
        togel = any(k in low for k in ["togel", "angka jitu", "sgp edisi"])
        dukun = any(k in low for k in ["dukun", "santet", "pelet", "pesugihan"])
        adult = any(k in low for k in ["seks", "bokep", "dewasa", "vcs"])
        if (loan or togel or dukun or adult) and not prize_scam:
            add(r, "HARASS", "灰产贷款/赌博/成人/巫术骚扰")

        # --- AD: clear carrier/merchant promo (only if currently wrong) ---
        carrier_promo = any(
            k in low
            for k in [
                "paket flash",
                "kuota",
                "bronet",
                "iring",
                "rbt",
                "mytelkomsel",
                "aktifkan",
                "*123*",
                "*808*",
                "grabcar",
                "grabtaxi",
                "diskon",
            ]
        ) and not prize_scam and not (phone_shop and personal)
        # Don't force AD over correct TRANSACTION for activation results
        txn_result = any(
            k in low
            for k in [
                "berhasil diaktifkan",
                "berhasil.",
                "isi ulang",
                "topup",
                "sisa kuota",
                "sudah di non-aktifkan",
                "telah aktif",
                "kode transaksi",
                "orderan sedang kami proses",
            ]
        ) or (
            "sisa kuota flash anda" in low
        )

        if L == "FRAUD" and carrier_promo and not prize_scam and not bank_ask:
            add(r, "AD", "运营商/正规促销误标诈骗")

        # orig=1 TRANSACTION that are recharge success with promo footer: keep TXN
        # only flip clear wrong TXN
        if L == "TRANSACTION" and phone_shop and personal:
            add(r, "FRAUD", "事务误标的灰产手机店")
        if L == "TRANSACTION" and prize_scam:
            add(r, "FRAUD", "事务误标的假中奖")
        if L == "TRANSACTION" and loan and not txn_result:
            add(r, "HARASS", "事务误标的贷款推销")

        # AD that is clearly txn result
        if L == "AD" and txn_result and not any(k in low for k in ["promo", "spesial untuk", "yuks", "ayo"]):
            # isi ulang berhasil / paket berhasil - TRANSACTION
            if any(
                k in low
                for k in [
                    "berhasil diaktifkan",
                    "isi ulang",
                    "topup",
                    "sisa kuota flash anda",
                    "sudah di non-aktifkan",
                    "kode transaksi",
                ]
            ):
                add(r, "TRANSACTION", "业务结果通知误标广告")

        # NEEDS_REVIEW clear fraud/loan
        if L == "NEEDS_REVIEW":
            if prize_scam or (phone_shop and personal and cheap):
                add(r, "FRAUD", "REVIEW漏标诈骗")
            elif loan or togel or dukun:
                add(r, "HARASS", "REVIEW漏标骚扰")

    # dedupe by id keep last
    by = {}
    for c in changes:
        by[c["id"]] = c
    return list(by.values())


def audit(rows):
    issues = Counter()
    for r in rows:
        t = (r.get("text") or "").lower()
        L = (r.get("label") or "").strip()
        personal = bool(re.search(r"08\d{8,}", r.get("text") or ""))
        if L == "AD" and any(k in t for k in ["blackberry", "bb dakota", "bb onyx"]) and personal:
            issues["AD_grey_phone"] += 1
        if L == "AD" and any(k in t for k in ["pemenang", "pin pemenang", "blogspot", "toyota yaris"]):
            issues["AD_prize_scam"] += 1
        if L == "TRANSACTION" and any(k in t for k in ["pemenang", "pin:", "blogspot"]):
            issues["TXN_prize"] += 1
        if L == "FRAUD" and any(k in t for k in ["mytelkomsel", "paket flash"]) and "pemenang" not in t:
            issues["FRAUD_carrier"] += 1
        if not (r.get("annotator") or "").strip():
            issues["empty_annotator"] += 1
    return dict(issues)


def main():
    if not BACKUP.exists():
        BACKUP.write_bytes(CSV_PATH.read_bytes())

    fields, rows = load_rows()
    by_id = {r["id"]: r for r in rows}

    rules = rule_fixes(rows)
    (ANN / "_fix_id_yudiwbs_rules.json").write_text(
        json.dumps({"changes": rules, "reviewed": len(rows)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    agent_path = ANN / "_fix_id_yudiwbs.json"
    agent_changes = []
    if agent_path.exists():
        agent_changes = json.loads(agent_path.read_text(encoding="utf-8")).get("changes", [])

    # merge: rules priority 100, agent 80
    best = {}
    for c in agent_changes:
        if c.get("new") in VALID and c.get("id"):
            best[c["id"]] = (80, c)
    for c in rules:
        best[c["id"]] = (100, c)

    applied = 0
    for rid, (_, c) in best.items():
        r = by_id.get(rid)
        if not r:
            continue
        old = (r.get("label") or "").strip()
        if old == c["new"]:
            continue
        r["label"] = c["new"]
        note = (r.get("notes") or "").strip()
        fix = f"[fix:{old}->{c['new']}] {c.get('reason', '')}"
        r["notes"] = (note + " | " + fix).strip(" |") if note else fix
        # keep/update label_reason if column exists
        if "label_reason" in r:
            r["label_reason"] = c.get("reason", r.get("label_reason", ""))
        applied += 1

    for r in rows:
        if not (r.get("annotator") or "").strip():
            r["annotator"] = "audit_fixpass_id"

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    out = {
        "applied": applied,
        "merged": len(best),
        "label_dist": dict(Counter((r.get("label") or "").strip() for r in rows)),
        "audit_remaining": audit(rows),
        "by_transition": {
            f"{a}->{b}": n
            for (a, b), n in Counter((c["old"], c["new"]) for _, c in best.values()).items()
        },
    }
    (ANN / "_id_yudiwbs_audit_after_fix.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
