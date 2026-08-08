#!/usr/bin/env python3
"""Read and patch the 7 missing annotations in the A file."""
import csv, sys
csv.field_size_limit(sys.maxsize)

INPATH = "training/data/interim/annotation/transaction_specialist/transaction_specialist_annotator_A.csv"

with open(INPATH, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    fieldnames = [fn.strip().strip('"') for fn in reader.fieldnames]
    reader.fieldnames = fieldnames
    rows = list(reader)
    # Clean keys
    for row in rows:
        cleaned = {}
        for k, v in row.items():
            kk = k.strip().strip('"')
            cleaned[kk] = v
        row.clear()
        row.update(cleaned)

ANNOTATOR = "HUMAN_A_001"

# The 7 specific IDs that were missed, plus their labels
patches = {
    "zh_01157": ("TRANSACTION", "浦发外币记账规则通知"),
    "zh_05356": ("TRANSACTION", "北京银行借记卡开通快捷支付"),
    "zh_05773": ("TRANSACTION", "政府一站通启动码"),
    "zh-n2w-03977": ("FRAUD", "游戏激活充值诈骗链接"),
    "zh-n2w-04389": ("TRANSACTION", "聚水潭系统授权短信验证码"),
    "zh-n2w-01141": ("FRAUD", "冒充银行通知兑换手机+钓鱼链接"),
    "zh-n2w-02538": ("FRAUD", "可疑还款链接冒充金融平台"),
}

count = 0
for row in rows:
    rid = row["id"]
    if rid in patches:
        row["label"] = patches[rid][0]
        row["human_annotator_id"] = ANNOTATOR
        row["notes"] = patches[rid][1]
        count += 1
        print(f"PATCHED: {rid} -> {patches[rid][0]}")

# Also set human_annotator_id for any that are missing it
for row in rows:
    if not row.get("human_annotator_id") or row["human_annotator_id"].strip() == "":
        row["human_annotator_id"] = ANNOTATOR
        # These are NEEDS_REVIEW default - add notes if empty
        if row["label"] == "NEEDS_REVIEW" and not row.get("notes", "").strip():
            row["notes"] = "无法分类需人工复核"

# Write back
with open(INPATH, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

# Verify
from collections import Counter
cnt = Counter(r["label"] for r in rows)
print(f"\nTotal: {len(rows)}")
print(f"Patched: {count}")
for lbl, n in sorted(cnt.items()):
    print(f"  {lbl}: {n}")

# Check for any remaining unlabeled
unlabeled = [r for r in rows if not r.get("label") or r["label"].strip() == ""]
print(f"Empty labels: {len(unlabeled)}")

# Check all have same annotator ID
ids_set = set(r["human_annotator_id"] for r in rows)
print(f"Annotator IDs: {ids_set}")
print("Verification: PASS" if ids_set == {ANNOTATOR} else "Verification: FAIL")

# Check need_review have notes
nr_no_notes = [r for r in rows if r["label"] == "NEEDS_REVIEW" and not r.get("notes", "").strip()]
print(f"NEEDS_REVIEW without notes: {len(nr_no_notes)}")
for r in nr_no_notes[:5]:
    print(f"  {r['id']}: {r['text'][:50]}")