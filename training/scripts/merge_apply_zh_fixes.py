#!/usr/bin/env python3
"""Merge agent+rule fixes and write corrected zh_all_suggested.csv."""
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
CSV_PATH = ANN / "zh_all_suggested.csv"
BACKUP = ANN / "zh_all_suggested.bak_before_fixpass.csv"
VALID = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}
PRIORITY = {
    "rule_based": 100,
    "_fix_rules.json": 100,
    "_fix_txn.json": 80,
    "_fix_fraud_harass.json": 80,
    "_fix_ad.json": 70,
    "_fix_review.json": 50,
    "post_unify": 120,
}


def load_rows():
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with CSV_PATH.open(encoding=enc, newline="") as fh:
                reader = csv.DictReader(fh)
                fields = list(reader.fieldnames or [])
                rows = list(reader)
            return enc, fields, rows
        except UnicodeDecodeError:
            continue
    raise RuntimeError("decode failed")


def main() -> None:
    if not BACKUP.exists():
        BACKUP.write_bytes(CSV_PATH.read_bytes())

    enc, fields, rows = load_rows()
    by = {r["id"]: r for r in rows}
    print(f"loaded {len(rows)} via {enc}")

    changes = []
    for name in (
        "_fix_rules.json",
        "_fix_txn.json",
        "_fix_fraud_harass.json",
        "_fix_ad.json",
        "_fix_review.json",
    ):
        path = ANN / name
        data = json.loads(path.read_text(encoding="utf-8"))
        for c in data.get("changes", []):
            c = dict(c)
            c["source"] = name
            changes.append(c)

    blocked = 0
    filtered = []
    for c in changes:
        if c.get("old") == "FRAUD" and c.get("new") == "AD":
            r = by.get(c["id"])
            t = (r.get("text") if r else "") or ""
            if any(
                k in t
                for k in [
                    "天上掉下个Iphone",
                    "v1x.cn",
                    "场外幸运",
                    "梦想秀",
                    "最强音",
                    "mxx",
                    "zgzqy",
                ]
            ):
                blocked += 1
                continue
        filtered.append(c)
    print("blocked_fraud_to_ad", blocked)

    best = {}
    for c in filtered:
        rid, new = c.get("id"), c.get("new")
        if not rid or new not in VALID:
            continue
        pr = PRIORITY.get(c.get("source"), 10)
        prev = best.get(rid)
        if prev is None or pr >= prev[0]:
            best[rid] = (pr, c)

    # Unify 双色球荐号 → HARASS; 已中奖结果 → TRANSACTION
    for r in rows:
        t = r.get("text") or ""
        rid = r["id"]
        old = (r.get("label") or "").strip()
        if "双色球" in t and ("专家推荐" in t or "自选回" in t):
            best[rid] = (
                120,
                {
                    "id": rid,
                    "old": old,
                    "new": "HARASS",
                    "reason": "双色球荐号/投注博彩招揽统一HARASS",
                    "source": "post_unify",
                },
            )
        elif "双色球" in t and "已中奖" in t and "专家推荐" not in t:
            best[rid] = (
                120,
                {
                    "id": rid,
                    "old": old,
                    "new": "TRANSACTION",
                    "reason": "已购彩票中奖结果通知",
                    "source": "post_unify",
                },
            )

    applied = 0
    for rid, (_, c) in best.items():
        r = by.get(rid)
        if not r:
            continue
        old = (r.get("label") or "").strip()
        if old == c["new"]:
            continue
        r["label"] = c["new"]
        note = (r.get("notes") or "").strip()
        fix = f"[fix:{old}->{c['new']}] {c.get('reason', '')}"
        r["notes"] = (note + " | " + fix).strip(" |") if note else fix
        applied += 1

    for r in rows:
        if not (r.get("annotator") or "").strip():
            r["annotator"] = "audit_fixpass"

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    issues = Counter()
    for r in rows:
        t = r.get("text") or ""
        L = (r.get("label") or "").strip()
        if (
            L == "TRANSACTION"
            and any(k in t for k in ["抵用券", "现金券", "积分抽奖"])
            and "验证码" not in t
            and "消费人民币" not in t
        ):
            issues["TXN_coupon"] += 1
        if (
            L == "AD"
            and any(k in t for k in ["当天放款", "无抵押"])
            and re.search(r"1[3-9]\d{9}", t)
            and not any(k in t for k in ["【平安银行】", "【中国平安】", "【工商银行】", "【招商银行】"])
        ):
            issues["AD_grey_loan"] += 1
        if L == "HARASS" and re.search(r"支付验证码\d+", t):
            issues["HARASS_otp"] += 1
        if (
            L == "FRAUD"
            and any(k in t for k in ["建仓", "涨停", "午盘", "带学员"])
            and not any(k in t for k in ["中奖", "安全账户", "领取", "保证金", "场外幸运"])
        ):
            issues["FRAUD_stock"] += 1
        if L == "AD" and "天上掉下个Iphone" in t:
            issues["AD_fake_iphone"] += 1
        if not (r.get("annotator") or "").strip():
            issues["empty_ann"] += 1

    out = {
        "applied": applied,
        "merged": len(best),
        "blocked_fraud_to_ad": blocked,
        "label_dist": dict(Counter((r.get("label") or "").strip() for r in rows)),
        "audit_remaining": dict(issues),
        "by_transition": {
            f"{a}->{b}": n
            for (a, b), n in Counter((c["old"], c["new"]) for _, c in best.values()).items()
        },
    }
    (ANN / "_zh_audit_after_fix.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ANN / "_fix_merged.json").write_text(
        json.dumps(
            {"n": len(best), "changes": [c for _, c in best.values()]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
