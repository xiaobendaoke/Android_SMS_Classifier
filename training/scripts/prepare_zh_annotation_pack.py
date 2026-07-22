#!/usr/bin/env python3
"""Prepare Chinese four-class annotation pack from gitcode 8a104 binary SMS set.

Input:
  training/data/raw/gitcode_zh_sms_8a104/zh_sms_binary.txt
  Format: <0|1>\\t<text>   (0=normal-ish, 1=spam-ish)

Output (local / gitignored under interim):
  training/data/interim/annotation/zh_all_suggested.csv
  training/data/interim/annotation/zh_pilot_800.csv
  training/data/interim/annotation/README_ZH_ANNOTATORS.txt
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "raw" / "gitcode_zh_sms_8a104" / "zh_sms_binary.txt"
DEFAULT_OUT_DIR = ROOT / "data" / "interim" / "annotation"

FIELDNAMES = [
    "id",
    "text",
    "language",
    "source",
    "binary_label",
    "suggested_label",
    "suggest_reason",
    "label",
    "annotator",
    "template_group",
    "notes",
]

TXN_RESULT_KEYS = [
    "验证码",
    "校验码",
    "动态码",
    "短信码",
    "扣款",
    "到账",
    "消费人民币",
    "消费成功",
    "支付成功",
    "交易成功",
    "尾号",
    "快递",
    "签收",
    "运单",
    "取件",
    "余量提醒",
    "流量剩余",
    "话费",
    "账单",
    "已使用",
    "剩余",
]
TXN_BLOCKERS = [
    "优惠",
    "促销",
    "折扣",
    "送礼",
    "办卡",
    "分期",
    "升档",
    "特惠",
    "开业",
    "到店",
]
FRAUD_KEYS = [
    "中奖",
    "领奖",
    "奖金",
    "点击链接",
    "点击查看",
    "账户异常",
    "安全账户",
    "公安",
    "检察院",
    "法院传",
    "冻结",
    "汇款",
    "转账到",
    "提供密码",
    "告知验证码",
    "把验证码",
    "秒杀资格",
    "恭喜您获得",
    "退税",
    "退款请先",
]
AD_KEYS = [
    "优惠",
    "促销",
    "特价",
    "打折",
    "到店",
    "开业",
    "团购",
    "红包",
    "售楼",
    "楼盘",
    "展会",
    "报名",
    "热线",
    "详询",
    "欢迎惠顾",
    "活动火热",
    "半价",
    "限量",
    "充值送",
    "办卡",
    "分期",
]
HARASS_KEYS = [
    "催收",
    "欠款",
    "逾期",
    "放款",
    "无抵押",
    "当天下款",
    "代开发票",
    "发票代开",
    "色情",
    "包夜",
    "加微信",
    "博彩",
    "赌博",
    "时时彩",
    "六合彩",
]


def template_group(text: str) -> str:
    key = re.sub(r"\d+", "#", text)
    key = re.sub(r"\s+", "", key)[:40]
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def looks_like_sms(text: str) -> bool:
    if not (4 <= len(text) <= 500):
        return False
    if len(text) > 180 and ("。。" in text or text.count("，") > 8):
        return False
    score = 0
    if len(text) <= 200:
        score += 1
    if re.search(r"\d{5,}", text):
        score += 1
    if any(k in text for k in TXN_RESULT_KEYS + FRAUD_KEYS + AD_KEYS + HARASS_KEYS):
        score += 2
    if re.search(r"(http|www\.|t\.cn|【|】|退订|回复)", text, re.I):
        score += 1
    return score >= 2


def suggest_label(binary: str, text: str) -> Tuple[str, str]:
    """Align with docs/labeling-guide.md decision order (FRAUD → TXN → AD → HARASS)."""
    # ① fraud first
    if any(k in text for k in FRAUD_KEYS):
        return "FRAUD", "fraud-intent-keywords"
    if re.search(r"(解冻|安全账户|异常.*点击|点击.*验证)", text):
        return "FRAUD", "social-engineering-pattern"

    # ② transaction: business result notice, not promo
    has_txn = any(k in text for k in TXN_RESULT_KEYS)
    has_promo = any(k in text for k in TXN_BLOCKERS + AD_KEYS)
    if has_txn and not has_promo:
        return "TRANSACTION", "account/order/auth/logistics-result"
    if has_txn and has_promo and any(k in text for k in ["验证码", "校验码", "扣款", "到账", "消费人民币", "支付成功"]):
        # OTP / hard payment result wins over trailing promo footer
        return "TRANSACTION", "hard-txn-signal-over-promo-footer"

    # ③ ad: clear commercial promo
    if any(k in text for k in AD_KEYS) or (binary == "1" and has_promo):
        return "AD", "merchant-promo"
    if binary == "1" and re.search(r"(http|www\.|t\.cn)", text, re.I) and not any(
        k in text for k in FRAUD_KEYS
    ):
        # bare promo/news links without clear fraud lexicon → AD candidate (human must check)
        return "AD", "spam-link-promo-candidate"

    # ④ harass
    if any(k in text for k in HARASS_KEYS):
        return "HARASS", "collection/gray/adult/gambling"

    if binary == "1":
        return "NEEDS_REVIEW", "spam-unclear"
    return "NEEDS_REVIEW", "normal-unclear"


def load_binary(path: Path) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        lab, text = line.split("\t", 1)
        lab = lab.strip()
        text = text.strip()
        if lab not in {"0", "1"} or not text:
            continue
        rows.append((lab, text))
    return rows


def write_csv(path: Path, records: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(records)


def balanced_pilot(records: List[dict], per_class: int, seed: int) -> List[dict]:
    rng = random.Random(seed)
    by: Dict[str, List[dict]] = defaultdict(list)
    for r in records:
        by[r["suggested_label"]].append(r)
    labels = ["TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"]
    picked: List[dict] = []
    for lab in labels:
        pool = by.get(lab, [])
        n = min(per_class, len(pool))
        if n:
            picked.extend(rng.sample(pool, n))
    # if still short of ~800, fill from remaining AD/TRANSACTION
    target = min(800, len(records))
    if len(picked) < target:
        remain = [r for r in records if r not in picked]
        need = target - len(picked)
        if remain:
            picked.extend(rng.sample(remain, min(need, len(remain))))
    rng.shuffle(picked)
    out = []
    for i, r in enumerate(picked):
        row = dict(r)
        row["id"] = f"zh_pilot_{i:04d}"
        out.append(row)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build Chinese annotation CSV pack.")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--per-class", type=int, default=160, help="Pilot samples per suggested class.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--keep-non-sms", action="store_true", help="Do not filter non-SMS-like rows.")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.input.exists():
        print(f"Missing input: {args.input}", file=sys.stderr)
        return 1

    pairs = load_binary(args.input)
    records: List[dict] = []
    skipped = 0
    for i, (binary, text) in enumerate(pairs):
        if not args.keep_non_sms and not looks_like_sms(text):
            skipped += 1
            continue
        suggested, reason = suggest_label(binary, text)
        records.append(
            {
                "id": f"zh_{i:05d}",
                "text": text,
                "language": "zh",
                "source": "gitcode_zh_sms_8a104",
                "binary_label": binary,
                "suggested_label": suggested,
                "suggest_reason": reason,
                "label": "",
                "annotator": "",
                "template_group": template_group(text),
                "notes": "",
            }
        )

    all_path = args.out_dir / "zh_all_suggested.csv"
    pilot_path = args.out_dir / "zh_pilot_800.csv"
    write_csv(all_path, records)
    pilot = balanced_pilot(records, args.per_class, args.seed)
    write_csv(pilot_path, pilot)

    # class counts
    from collections import Counter

    c_all = Counter(r["suggested_label"] for r in records)
    c_pilot = Counter(r["suggested_label"] for r in pilot)

    readme = args.out_dir / "README_ZH_ANNOTATORS.txt"
    readme.write_text(
        "\n".join(
            [
                "中文四分类标注说明（作业用）",
                "",
                "请打开：zh_pilot_800.csv",
                "",
                "你只要填两列：",
                "  1) label = TRANSACTION / AD / HARASS / FRAUD / NEEDS_REVIEW",
                "  2) annotator = 你的名字",
                "",
                "判断顺序：",
                "  1. 验证码/银行扣款到账/套餐话费/快递取件 → TRANSACTION",
                "  2. 中奖钓鱼/要密码/假公检法/诱导转账 → FRAUD",
                "  3. 正常商家促销到店优惠 → AD",
                "  4. 贷款催收/色情博彩/扰民推销 → HARASS",
                "  5. 不确定 → NEEDS_REVIEW",
                "",
                "注意：",
                "  - suggested_label 只是机器建议，请人工确认后写入 label",
                "  - binary_label: 0=原数据集正常, 1=原数据集垃圾",
                "  - 不要把 NEEDS_REVIEW 硬改成四类",
                "",
                f"过滤后候选：{len(records)} 条（跳过不像短信 {skipped} 条）",
                f"全量建议分布：{dict(c_all)}",
                f"试点分布：{dict(c_pilot)}",
                "",
                "建议进度：今晚先标 50 条；本周尽量标完 zh_pilot_800.csv",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"raw pairs: {len(pairs)}")
    print(f"kept sms-like: {len(records)} (skipped {skipped})")
    print(f"suggested dist: {dict(c_all)}")
    print(f"Wrote {all_path}")
    print(f"Wrote {pilot_path} n={len(pilot)} dist={dict(c_pilot)}")
    print(f"Wrote {readme}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
