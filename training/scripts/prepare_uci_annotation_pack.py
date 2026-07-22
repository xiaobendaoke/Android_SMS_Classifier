#!/usr/bin/env python3
"""Prepare English four-class annotation pack from UCI SMS Spam Collection.

Input:
  training/data/raw/uci_sms_spam/extracted/SMSSpamCollection
  (fallback: training/data/raw/uci_sms_spam/SMSSpamCollection)

Output (local / gitignored under interim):
  training/data/interim/annotation/uci_all_suggested.csv
  training/data/interim/annotation/uci_pilot_500.csv
  training/data/interim/annotation/README_EN_ANNOTATORS.txt

Decision order matches docs/labeling-guide.md:
  FRAUD → TRANSACTION → AD → HARASS → NEEDS_REVIEW
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUTS = [
    ROOT / "data" / "raw" / "uci_sms_spam" / "extracted" / "SMSSpamCollection",
    ROOT / "data" / "raw" / "uci_sms_spam" / "SMSSpamCollection",
]
DEFAULT_OUT_DIR = ROOT / "data" / "interim" / "annotation"

FIELDNAMES = [
    "id",
    "text",
    "language",
    "source",
    "uci_binary",
    "suggested_label",
    "suggest_reason",
    "label",
    "annotator",
    "template_group",
    "notes",
]

# ① Fraud: deception / fake reward / social engineering (UCI classic UK prize SMS)
FRAUD_KEYS = [
    "you have won",
    "you've won",
    "you have been selected",
    "u have been specially selected",
    "winner!!",
    "winner!",
    " cash prize",
    "prize reward",
    "prize guaranteed",
    "bonus prize",
    "claim code",
    "claim your",
    "to claim call",
    "to claim txt",
    "call now to claim",
    "guaranteed £",
    "guaranteed $",
    "jackpot",
    "lottery",
    "awarded a complimentary",
    "awarded £",
    "awarded $",
    "bonus caller prize",
    "unredeemed bonus",
    "account statement for 0",
    "private! your",
    "final try to contact",
    "won a guaranteed",
    "won a 1 week",
    "won a £",
    "won a $",
]
FRAUD_PATTERNS = [
    r"\bwon\b.{0,40}\b(prize|cash|£|\$|award)",
    r"\b(prize|award|jackpot)\b.{0,40}\b(claim|call|txt|text)\b",
    r"\burgent[! ]*.{0,20}\b(won|award|prize|claim)\b",
    r"\baccount statement\b.{0,80}\b(claim|bonus|unredeemed)\b",
    r"\bfree\b.{0,30}\b(nokia|iphone|mobile)\b.{0,40}\b(call|claim)\b",
]

# ② Transaction: genuine business-result notices (rare in UCI ham)
TXN_KEYS = [
    "verification code",
    "one-time password",
    "one time password",
    "otp is",
    "otp:",
    "your otp",
    "your code is",
    "security code",
    "auth code",
    "transaction id",
    "has been credited",
    "has been debited",
    "account has been refilled",
    "prepaid account balance",
    "out for delivery",
    "tracking number",
    "parcel has",
    "package has been",
    "delivered to",
    "booking confirmed",
    "appointment confirmed",
    "order confirmed",
    "payment received",
    "payment successful",
]
TXN_BLOCKERS = [
    "claim",
    "prize",
    "won",
    "winner",
    "jackpot",
    "lottery",
    "free entry",
    "ringtone",
    "sexy",
    "xxx",
    "dating",
    "horny",
]

# ③ Ad: commercial promo / content subscription (not fake-win)
AD_KEYS = [
    "ringtone",
    "free msg",
    "freemsg",
    "unsubscribe",
    "stop to end",
    "reply stop",
    "txt stop",
    "text stop",
    "% off",
    "percent off",
    "discount",
    "special offer",
    "limited offer",
    "sale!",
    "subscribe",
    "subscription to",
    "will be charged",
    "mobile will be charged",
    "update to the latest",
    "new mobiles",
    "camera for free",
    "free nokia",
    "collect yours",
    "std txt rate",
    "tsandcs",
    "t&c's",
    "16+",
    "18+",
    "wkly comp",
    "weekly quiz",
    "txt ur national",
    "sports",
    "cinema pass",
]

# ④ Harass: adult / dating grey / debt — not classic prize fraud
HARASS_KEYS = [
    "xxx",
    "sexy",
    "adult",
    "dating",
    "dogging",
    "horny",
    "get laid",
    "hardcore",
    "chat svc",
    "chat service",
    "secret admirer",
    "meet someone sexy",
    "find a date",
    "flirt",
    "booty",
    "naked",
    "debt",
    "overdue",
    "collection agency",
    "owe",
]


def template_group(text: str) -> str:
    key = re.sub(r"\d+", "#", text.lower())
    key = re.sub(r"[^a-z#]+", " ", key)
    key = " ".join(key.split()[:10])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def suggest_label(uci_binary: str, text: str) -> Tuple[str, str]:
    """Heuristic only. Align with docs/labeling-guide.md (FRAUD first)."""
    t = text.lower()
    spam = uci_binary == "spam"

    # ① fraud first
    if any(k in t for k in FRAUD_KEYS):
        return "FRAUD", "fraud-intent-keywords"
    if any(re.search(p, t) for p in FRAUD_PATTERNS):
        return "FRAUD", "fraud-social-engineering-pattern"
    # "password" used as ringtone unlock word is AD, not fraud OTP theft
    if re.search(r"\b(password|pin|verify)\b", t) and re.search(
        r"\b(claim|prize|won|urgent|account.*(suspend|frozen|lock))\b", t
    ):
        return "FRAUD", "credential-or-urgent-scam"

    # ② transaction: business result, not promo/fraud bait
    has_txn = any(k in t for k in TXN_KEYS)
    has_blocker = any(k in t for k in TXN_BLOCKERS)
    if has_txn and not has_blocker:
        return "TRANSACTION", "account/order/auth/logistics-result"
    if has_txn and has_blocker and any(
        k in t for k in ["verification code", "one-time password", "otp is", "transaction id"]
    ):
        return "TRANSACTION", "hard-txn-signal-over-noise"

    # ③ ad: clear commercial / subscription marketing
    if any(k in t for k in AD_KEYS):
        return "AD", "merchant-or-subscription-promo"
    if spam and re.search(r"(http://|https://|www\.|wap\.)", t) and not any(
        k in t for k in FRAUD_KEYS + HARASS_KEYS
    ):
        return "AD", "spam-link-promo-candidate"

    # ④ harass
    if any(k in t for k in HARASS_KEYS):
        return "HARASS", "adult-dating-debt-harass"

    if spam:
        return "NEEDS_REVIEW", "spam-unclear-subtype"
    # Most UCI ham is personal chat — do NOT auto-label as TRANSACTION
    return "NEEDS_REVIEW", "ham-personal-or-unclear"


def load_uci(path: Path) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        if "\t" in line:
            label, text = line.split("\t", 1)
        else:
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            label, text = parts
        label = label.strip().lower()
        if label not in {"ham", "spam"}:
            continue
        rows.append((label, text.strip()))
    return rows


def write_csv(path: Path, records: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)


def balanced_pilot(records: List[dict], n: int, seed: int) -> List[dict]:
    """Cover all four classes + enough NEEDS_REVIEW (personal chat practice)."""
    rng = random.Random(seed)
    by: Dict[str, List[dict]] = defaultdict(list)
    for r in records:
        by[r["suggested_label"]].append(r)

    # Reserve ~30% for NEEDS_REVIEW so annotators practice "don't force TRANSACTION on ham"
    n_review = min(len(by["NEEDS_REVIEW"]), max(120, n * 3 // 10))
    remain_budget = n - n_review

    # UCI has almost no true TRANSACTION — take all, then split rest across FRAUD/AD/HARASS
    n_txn = min(len(by["TRANSACTION"]), remain_budget)
    rest = remain_budget - n_txn
    n_fraud = min(len(by["FRAUD"]), max(80, rest // 3))
    n_ad = min(len(by["AD"]), max(80, rest // 3))
    n_harass = min(len(by["HARASS"]), rest - n_fraud - n_ad)
    if n_harass < 0:
        n_harass = 0
        # shrink AD/FRAUD if needed
        overflow = n_fraud + n_ad - rest
        if overflow > 0:
            cut_ad = min(n_ad, overflow)
            n_ad -= cut_ad
            overflow -= cut_ad
            n_fraud = max(0, n_fraud - overflow)

    quotas = {
        "TRANSACTION": n_txn,
        "FRAUD": n_fraud,
        "AD": n_ad,
        "HARASS": n_harass,
        "NEEDS_REVIEW": n_review,
    }

    picked: List[dict] = []
    used_ids = set()
    for lab, k in quotas.items():
        pool = by.get(lab, [])
        k = min(k, len(pool))
        if k <= 0:
            continue
        for r in rng.sample(pool, k):
            picked.append(r)
            used_ids.add(id(r))

    # Top up if short
    if len(picked) < n:
        remain = [r for r in records if id(r) not in used_ids]
        rng.shuffle(remain)
        for r in remain[: n - len(picked)]:
            picked.append(r)

    rng.shuffle(picked)
    picked = picked[:n]

    out: List[dict] = []
    for i, r in enumerate(picked):
        row = dict(r)
        row["id"] = f"uci_pilot_{i:04d}"
        out.append(row)
    return out


def write_readme(path: Path, all_n: int, pilot_n: int, dist: Counter) -> None:
    dist_lines = [f"  {k}: {dist.get(k, 0)}" for k in ["TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"]]
    path.write_text(
        "\n".join(
            [
                "英文四分类标注说明（UCI，已与中文主规格对齐）",
                "",
                "打开文件：uci_pilot_500.csv",
                "填写两列：",
                "  - label：TRANSACTION / AD / HARASS / FRAUD / NEEDS_REVIEW",
                "  - annotator：你的名字",
                "",
                "════════════════════════════════════",
                "一、四类定义（先看懂再标）",
                "════════════════════════════════════",
                "TRANSACTION 事务：用户预期要收到的业务结果",
                "  （OTP/验证码、扣款到账、账单、物流取件、订单确认等）",
                "",
                "AD 广告：正规商家/内容服务促销，目的是让你买/订购",
                "  （铃声订阅、手机升级优惠、商店打折、退订类营销——不骗你转账）",
                "",
                "HARASS 骚扰：不靠“骗转账”，但内容扰民",
                "  （成人/约炮短信、灰色交友、催收、反复骚扰推销）",
                "",
                "FRAUD 诈骗：靠欺骗造成损失",
                "  （假中奖、假积分/账单要你回电领奖、钓鱼链接、冒充客服要码要钱）",
                "",
                "不确定 → NEEDS_REVIEW（不要硬猜）",
                "  ★ UCI 里大量 ham 是私人闲聊 → 一律 NEEDS_REVIEW，不要硬塞 TRANSACTION",
                "",
                "════════════════════════════════════",
                "二、强制判断顺序（必须按这个顺序问）",
                "════════════════════════════════════",
                "① 是不是在骗我？（假中奖/假奖励/要码要钱/钓鱼/假账单领奖）",
                "     → 是：FRAUD",
                "② 是不是账户/订单/认证/物流等“业务结果告知”？",
                "     → 是：TRANSACTION",
                "③ 是不是正规商家/内容服务在促销、拉订阅？",
                "     → 是：AD",
                "④ 是不是成人/交友灰产/催收/强行推销（但不是典型诈骗）？",
                "     → 是：HARASS",
                "⑤ 其他 → NEEDS_REVIEW",
                "",
                "注意：不是「ham 就标事务」！也不是「有 link 就标诈骗」！",
                "      不是「spam 就标诈骗」——很多 spam 是铃声/促销广告或成人骚扰。",
                "",
                "════════════════════════════════════",
                "三、UCI 英文易混例子（标错最多的）",
                "════════════════════════════════════",
                "WINNER!! £900 prize reward. To claim call 09...     → FRAUD",
                "Private! Account Statement... Bonus Points. Claim → FRAUD",
                "Your account refilled. Transaction ID KR...         → TRANSACTION",
                "Delivery: your parcel is out for delivery           → TRANSACTION",
                "Thanks for Ringtone UK subscription, £5/month       → AD",
                "Update to latest colour mobiles Free! Call 0800...  → AD",
                "Want 2 get laid tonight? Txt GRAVEL to 69888        → HARASS",
                "FreeMsg... sexy female... 150p per msg              → HARASS",
                "Hey, running late, see you at 4                     → NEEDS_REVIEW",
                "Can you send me your account number? (朋友聊天)      → NEEDS_REVIEW",
                "",
                "════════════════════════════════════",
                "四、其他",
                "════════════════════════════════════",
                "- suggested_label 仅机器粗分，请按上面规则改 label",
                "- uci_binary：ham/spam 是原二分类，不等于四类",
                "- 全量建议粗分（机器，仅供参考）：",
                *dist_lines,
                "- 完整说明：docs/labeling-guide.md（含英文补充）",
                "- 待办清单：docs/en-annotation-todo.md",
                "",
                f"全量：uci_all_suggested.csv（{all_n} 条）",
                f"试点：uci_pilot_500.csv（{pilot_n} 条）",
                "",
                "进度：先标 50 条练手，再尽量标完 500 条。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def resolve_input(explicit: Optional[Path]) -> Path:
    if explicit is not None:
        return explicit
    for p in DEFAULT_INPUTS:
        if p.exists():
            return p
    return DEFAULT_INPUTS[0]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build UCI English four-class annotation CSV pack.")
    p.add_argument("--input", type=Path, default=None)
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--pilot-size", type=int, default=500)
    p.add_argument("--seed", type=int, default=42)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = resolve_input(args.input)
    if not input_path.exists():
        print(f"UCI file missing: {input_path}", file=sys.stderr)
        print("Expected download under training/data/raw/uci_sms_spam/", file=sys.stderr)
        return 1

    pairs = load_uci(input_path)
    records: List[dict] = []
    for i, (binary, text) in enumerate(pairs):
        suggested, reason = suggest_label(binary, text)
        records.append(
            {
                "id": f"uci_{i:05d}",
                "text": text,
                "language": "en",
                "source": "uci_sms_spam_collection_v1",
                "uci_binary": binary,
                "suggested_label": suggested,
                "suggest_reason": reason,
                "label": "",
                "annotator": "",
                "template_group": template_group(text),
                "notes": "",
            }
        )

    dist = Counter(r["suggested_label"] for r in records)
    all_path = args.out_dir / "uci_all_suggested.csv"
    pilot_path = args.out_dir / "uci_pilot_500.csv"
    write_csv(all_path, records)
    pilot = balanced_pilot(records, args.pilot_size, args.seed)
    write_csv(pilot_path, pilot)

    readme = args.out_dir / "README_EN_ANNOTATORS.txt"
    write_readme(readme, len(records), len(pilot), dist)
    # keep short pointer for old path name
    (args.out_dir / "README_FOR_ANNOTATORS.txt").write_text(
        "请改看 README_EN_ANNOTATORS.txt（英文四分类标准已重写，与中文一致）。\n",
        encoding="utf-8",
    )

    pilot_dist = Counter(r["suggested_label"] for r in pilot)
    print(f"Loaded UCI rows: {len(records)}")
    print(f"Suggested distribution (all): {dict(dist)}")
    print(f"Suggested distribution (pilot): {dict(pilot_dist)}")
    print(f"Wrote {all_path}")
    print(f"Wrote {pilot_path} (n={len(pilot)})")
    print(f"Wrote {readme}")
    print("Next: open uci_pilot_500.csv and fill column 'label'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
