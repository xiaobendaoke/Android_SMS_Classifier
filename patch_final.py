#!/usr/bin/env python3
"""Apply final annotations directly to the CSV."""
import csv, sys
csv.field_size_limit(sys.maxsize)

INPATH = "training/data/interim/annotation/transaction_specialist/transaction_specialist_annotator_A.csv"
ANNOTATOR = "HUMAN_A_001"

with open(INPATH, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    fieldnames = [fn.strip().strip('"') for fn in reader.fieldnames]
    reader.fieldnames = fieldnames
    rows = list(reader)
    # Clean row keys
    for row in rows:
        for old_k in list(row.keys()):
            new_k = old_k.strip().strip('"')
            if new_k != old_k:
                row[new_k] = row.pop(old_k)

print(f"Read {len(rows)} rows, headers: {fieldnames}")

# Define patches: id -> (label, note)
patches = {}

def p(rid, label, note=""):
    patches[rid] = (label, note)

# === FRAUD ===
p("zh-n2w-03977", "FRAUD", "游戏激活诈骗链接，诱导点击")
p("zh-n2w-01141", "FRAUD", "冒充银行通知兑换手机，诈骗钓鱼链接")
p("zh-n2w-02538", "FRAUD", "冒充金融平台引导点击可疑还款链接")

# === TRANSACTION (currently NR without notes) ===
p("zh_01157", "TRANSACTION", "浦发银行外币记账规则通知")
p("zh_05356", "TRANSACTION", "北京银行借记卡开通支付宝快捷支付")
p("zh_05773", "TRANSACTION", "政府一站通账户启动码")
p("zh-n2w-04389", "TRANSACTION", "聚水潭系统授权验证码")

# Apply patches
count = 0
for row in rows:
    rid = row["id"]
    rid_clean = rid.strip()
    if rid_clean in patches:
        row["label"] = patches[rid_clean][0]
        row["human_annotator_id"] = ANNOTATOR
        row["notes"] = patches[rid_clean][1]
        count += 1
        print(f"  PATCHED: {rid_clean} -> {patches[rid_clean][0]}")

print(f"\nPatched {count} records")

# Ensure all rows have human_annotator_id
for row in rows:
    hid = row.get("human_annotator_id", "").strip()
    if not hid:
        row["human_annotator_id"] = ANNOTATOR

# Check final state
from collections import Counter
cnt = Counter(r["label"] for r in rows)
print(f"\nFinal counts ({len(rows)} total):")
for lbl, n in sorted(cnt.items()):
    print(f"  {lbl}: {n}")

# Check NEEDS_REVIEW without notes
nr_no_notes = [r for r in rows if r["label"] == "NEEDS_REVIEW" and not r.get("notes", "").strip()]
if nr_no_notes:
    print(f"\nWARNING: {len(nr_no_notes)} NEEDS_REVIEW without notes:")
    for r in nr_no_notes:
        print(f"  {r['id']}: {r.get('text','')[:60]}")
else:
    print("\nAll NEEDS_REVIEW have notes. OK!")

# Check annotator ID consistency
ids_set = set(r.get("human_annotator_id","") for r in rows)
print(f"Annotator IDs: {ids_set}")
if ids_set == {ANNOTATOR}:
    print("Annotator IDs consistent: OK")
else:
    print(f"WARNING: Expected {ANNOTATOR}, got {ids_set}")

# Write
with open(INPATH, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

print("\nFile written successfully.")