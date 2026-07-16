#!/usr/bin/env python3
"""Generate expanded synthetic multilingual SMS JSONL for pipeline demos.

Produces raw + processed splits with group-aware variety. All data is synthetic
(CC0 / Apache-2.0). Not a substitute for real labeled corpora for ≥98% claims.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List, Tuple

SEED = 42
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
MANIFESTS = ROOT / "data" / "manifests"

LABELS = ("TRANSACTION", "AD", "HARASS", "FRAUD")
LANGS = ("zh", "en", "hi", "id")

TEMPLATES: Dict[str, Dict[str, List[str]]] = {
    "TRANSACTION": {
        "zh": [
            "【银行】您的账户入账人民币{amount}元，余额{balance}元。",
            "支付宝：您于今日消费{amount}元，商户名称为{merchant}。",
            "航班{flight}已值机成功，登机口{gate}，起飞时间{time}。",
            "您的订单#{order}已发货，预计明日送达。",
            "水电费账单已出，本期应缴{amount}元，请于月底前缴纳。",
            "验证码{otp}，用于登录，请勿泄露。",
            "快递已到达{place}，请凭取件码{otp}领取。",
        ],
        "en": [
            "Your payment of ${amount} was received. Thank you.",
            "Flight {flight} is on time. Gate {gate}, boarding at {time}.",
            "Order #{order} shipped via FedEx. Track at example.com/track",
            "Direct deposit of ${amount} posted to account ending {last4}.",
            "Your OTP is {otp}. Do not share it.",
            "Package arrived at {place}. Pickup code {otp}.",
        ],
        "hi": [
            "आपका भुगतान ₹{amount} स्वीकार किया गया। धन्यवाद।",
            "आपका टिकट पुष्टि हो गया है। यात्रा की शुभकामनाएँ।",
            "बिजली बिल ₹{amount} जारी किया गया है।",
            "आपका OTP {otp} है। साझा न करें।",
        ],
        "id": [
            "Pembayaran Anda sebesar Rp{amount} telah diterima.",
            "Pesanan #{order} telah dikirim. Estimasi tiba besok.",
            "Tiket kereta Anda telah dikonfirmasi.",
            "Kode OTP Anda {otp}. Jangan bagikan.",
        ],
    },
    "AD": {
        "zh": [
            "【限时优惠】全场{pct}折，点击领取专属优惠券！",
            "恭喜您获得免费抽奖机会，回复1参与领奖。",
            "新品上市，注册即送{amount}元红包，速来抢购。",
            "会员专享：升级套餐立减{amount}元，详情点击链接。",
        ],
        "en": [
            "Limited offer! Click now to claim your free gift card.",
            "You won a prize! Reply YES to receive your reward.",
            "Flash sale ends tonight. Shop now and save {pct}%.",
            "Exclusive deal: save ${amount} on your next order.",
        ],
        "hi": [
            "मुफ्त इनाम जीतें! अभी क्लिक करें और ऑफर पाएं।",
            "सीमित समय छूट! अभी खरीदें और {pct}% बचाएं।",
        ],
        "id": [
            "Promo diskon {pct}%! Klik di sini untuk klaim hadiah.",
            "Gratis ongkir hari ini. Belanja sekarang!",
        ],
    },
    "HARASS": {
        "zh": [
            "你再不还钱我就去你公司找你，别装看不见。",
            "天天给你打电话你怎么不接？必须今天答复。",
            "别以为拉黑我就没办法，我总有办法联系你。",
        ],
        "en": [
            "Pay me back now or I will keep calling you every hour.",
            "Answer my messages. I know where you work.",
            "Stop ignoring me or I will contact your manager.",
        ],
        "hi": [
            "तुम्हारा पैसा वापस करो वरना मैं तुम्हें परेशान करूंगा।",
            "मेरा फोन उठाओ, मैं बार-बार कॉल करूंगा।",
        ],
        "id": [
            "Bayar utangmu sekarang atau saya akan terus menghubungi.",
            "Jangan abaikan pesan saya. Saya tahu alamatmu.",
        ],
    },
    "FRAUD": {
        "zh": [
            "【紧急】您的银行卡异常，请立即点击链接验证身份。",
            "社保账户即将冻结，请发送验证码到本号码解冻。",
            "快递丢失理赔，添加客服微信领取赔偿金。",
            "您的账户存在风险，请登录 http://fake-id.example 处理。",
        ],
        "en": [
            "Your account is locked. Verify immediately at http://secure-fake.example",
            "IRS refund pending. Send your SSN and card details to claim.",
            "Package held. Pay a small fee via this link to release delivery.",
            "Unusual login detected. Confirm OTP {otp} on this number.",
        ],
        "hi": [
            "आपका खाता ब्लॉक है। तुरंत सत्यापन लिंक पर क्लिक करें।",
            "आपका बैंक खाता असामान्य है, OTP भेजें।",
        ],
        "id": [
            "Akun Anda diblokir. Klik tautan verifikasi segera.",
            "Paket tertahan. Bayar biaya kecil lewat link ini.",
        ],
    },
}


def fill(template: str, rng: random.Random) -> str:
    return template.format(
        amount=rng.randint(10, 9999),
        balance=rng.randint(100, 99999),
        merchant=rng.choice(["便利店", "Coffee", "Toko", "दुकान"]),
        flight=f"{rng.choice(['CA', 'UA', 'GA'])}{rng.randint(100, 9999)}",
        gate=f"{rng.choice(['A', 'B', 'C'])}{rng.randint(1, 30)}",
        time=f"{rng.randint(6, 22):02d}:{rng.choice(['00', '15', '30', '45'])}",
        order=rng.randint(10000, 99999),
        otp=f"{rng.randint(100000, 999999)}",
        place=rng.choice(["菜鸟驿站", "lobby", "gerai", "केंद्र"]),
        last4=rng.randint(1000, 9999),
        pct=rng.choice([30, 40, 50, 60, 70]),
    )


def make_record(
    rid: str,
    text: str,
    label: str,
    language: str,
    sender_group: str,
    template_group: str,
    split: str,
    is_adversarial: bool = False,
) -> dict:
    license_id = "CC0" if hash(rid) % 2 == 0 else "Apache-2.0"
    return {
        "id": rid,
        "text": text,
        "label": label,
        "language": language,
        "source": "synthetic_public_v2",
        "source_license": license_id,
        "sender_group": sender_group,
        "template_group": template_group,
        "is_synthetic": True,
        "is_adversarial": is_adversarial,
        "parent_id": None,
        "annotator_ids": ["synthetic-generator-v2"],
        "split": split,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate expanded synthetic SMS dataset.")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--per-label-lang", type=int, default=40, help="Samples per label×lang.")
    p.add_argument("--adversarial-ratio", type=float, default=0.1)
    return p


def main(argv: List[str] | None = None) -> int:
    """Write raw JSONL only. Splits must be created by build_dataset.py (group-aware)."""
    args = build_parser().parse_args(argv)
    rng = random.Random(args.seed)
    RAW.mkdir(parents=True, exist_ok=True)
    MANIFESTS.mkdir(parents=True, exist_ok=True)

    records: List[dict] = []
    for label in LABELS:
        for lang in LANGS:
            templates = TEMPLATES[label].get(lang) or TEMPLATES[label]["en"]
            for i in range(args.per_label_lang):
                tpl = templates[i % len(templates)]
                text = fill(tpl, rng)
                # One group per template index — variants stay in the same group.
                tpl_group = f"tpl-{label.lower()}-{lang}-{i % len(templates)}"
                snd = f"snd-{label.lower()}-{lang}-{i % 5}"
                rid = f"syn-{label[:3].lower()}-{lang}-{i:04d}"
                # Adversarial train variants are created after split in build_dataset --augment-train.
                records.append(
                    make_record(rid, text, label, lang, snd, tpl_group, "train", False)
                )

    raw_path = RAW / "synthetic_v2.jsonl"
    raw_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )

    summary = {
        "seed": args.seed,
        "total": len(records),
        "raw_path": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
        "per_label_lang": args.per_label_lang,
        "note": (
            "Synthetic raw only. Run build_dataset.py for group-aware splits. "
            "Business metrics pending real labeled data."
        ),
    }
    (MANIFESTS / "synthetic_v2_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    print(f"Wrote raw {raw_path}")
    print("Next: python training/scripts/build_dataset.py [--augment-train]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
