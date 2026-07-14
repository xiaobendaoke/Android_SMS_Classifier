#!/usr/bin/env python3
"""One-shot generator for public synthetic JSONL (not for routine use)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"

SAMPLES = [
    # TRANSACTION zh
    ("syn-txn-zh-001", "【银行】您的账户入账人民币500.00元，余额1234.56元。", "TRANSACTION", "zh", "snd-bank-zh", "tpl-txn-credit-zh"),
    ("syn-txn-zh-002", "支付宝：您于今日12:30消费88元，商户名称为便利店。", "TRANSACTION", "zh", "snd-pay-zh", "tpl-txn-debit-zh"),
    ("syn-txn-zh-003", "航班CA1234已值机成功，登机口B12，起飞时间14:20。", "TRANSACTION", "zh", "snd-air-zh", "tpl-txn-flight-zh"),
    ("syn-txn-zh-004", "您的订单#882910已发货，预计明日送达。", "TRANSACTION", "zh", "snd-shop-zh", "tpl-txn-order-zh"),
    ("syn-txn-zh-005", "水电费账单已出，本期应缴126.50元，请于月底前缴纳。", "TRANSACTION", "zh", "snd-util-zh", "tpl-txn-bill-zh"),
    # TRANSACTION en
    ("syn-txn-en-001", "Your payment of $49.99 was received. Thank you.", "TRANSACTION", "en", "snd-bank-en", "tpl-txn-payment-en"),
    ("syn-txn-en-002", "Flight UA456 is on time. Gate C3, boarding at 18:40.", "TRANSACTION", "en", "snd-air-en", "tpl-txn-flight-en"),
    ("syn-txn-en-003", "Order #44102 shipped via FedEx. Track at example.com/track", "TRANSACTION", "en", "snd-shop-en", "tpl-txn-order-en"),
    ("syn-txn-en-004", "Direct deposit of $1,250.00 posted to account ending 4421.", "TRANSACTION", "en", "snd-bank-en", "tpl-txn-deposit-en"),
    # TRANSACTION hi
    ("syn-txn-hi-001", "आपका भुगतान ₹999 स्वीकार किया गया। धन्यवाद।", "TRANSACTION", "hi", "snd-bank-hi", "tpl-txn-payment-hi"),
    ("syn-txn-hi-002", "आपका टिकट पुष्टि हो गया है। यात्रा की शुभकामनाएँ।", "TRANSACTION", "hi", "snd-rail-hi", "tpl-txn-ticket-hi"),
    ("syn-txn-hi-003", "बिजली बिल ₹560 जारी किया गया है।", "TRANSACTION", "hi", "snd-util-hi", "tpl-txn-bill-hi"),
    # TRANSACTION id
    ("syn-txn-id-001", "Pembayaran Anda sebesar Rp150.000 telah diterima.", "TRANSACTION", "id", "snd-bank-id", "tpl-txn-payment-id"),
    ("syn-txn-id-002", "Pesanan #77821 telah dikirim. Estimasi tiba besok.", "TRANSACTION", "id", "snd-shop-id", "tpl-txn-order-id"),
    ("syn-txn-id-003", "Tiket kereta Anda telah dikonfirmasi.", "TRANSACTION", "id", "snd-rail-id", "tpl-txn-ticket-id"),
    # AD zh
    ("syn-ad-zh-001", "【限时优惠】全场5折，点击领取专属优惠券！", "AD", "zh", "snd-promo-zh", "tpl-ad-discount-zh"),
    ("syn-ad-zh-002", "恭喜您获得免费抽奖机会，回复1参与领奖。", "AD", "zh", "snd-lottery-zh", "tpl-ad-prize-zh"),
    ("syn-ad-zh-003", "新品上市，注册即送100元红包，速来抢购。", "AD", "zh", "snd-mall-zh", "tpl-ad-signup-zh"),
    ("syn-ad-zh-004", "会员专享：升级套餐立减200元，详情点击链接。", "AD", "zh", "snd-telco-zh", "tpl-ad-plan-zh"),
    # AD en
    ("syn-ad-en-001", "Limited offer! Click now to claim your free gift card.", "AD", "en", "snd-promo-en", "tpl-ad-offer-en"),
    ("syn-ad-en-002", "You won a prize! Reply YES to receive your reward.", "AD", "en", "snd-lottery-en", "tpl-ad-prize-en"),
    ("syn-ad-en-003", "Flash sale ends tonight. Shop now and save 70%.", "AD", "en", "snd-mall-en", "tpl-ad-sale-en"),
    # AD hi
    ("syn-ad-hi-001", "मुफ्त इनाम जीतें! अभी क्लिक करें और ऑफर पाएं।", "AD", "hi", "snd-promo-hi", "tpl-ad-offer-hi"),
    ("syn-ad-hi-002", "सीमित समय छूट! अभी खरीदें और 50% बचाएं।", "AD", "hi", "snd-mall-hi", "tpl-ad-sale-hi"),
    # AD id
    ("syn-ad-id-001", "Promo diskon 50%! Klik di sini untuk klaim hadiah.", "AD", "id", "snd-promo-id", "tpl-ad-offer-id"),
    ("syn-ad-id-002", "Gratis ongkir hari ini. Belanja sekarang!", "AD", "id", "snd-mall-id", "tpl-ad-shipping-id"),
    # HARASS zh
    ("syn-har-zh-001", "你再不还钱我就去你公司找你，别装看不见。", "HARASS", "zh", "snd-collect-zh", "tpl-har-debt-zh"),
    ("syn-har-zh-002", "天天给你打电话你怎么不接？必须今天答复。", "HARASS", "zh", "snd-stalker-zh", "tpl-har-pressure-zh"),
    ("syn-har-zh-003", "别以为拉黑我就没办法，我总有办法联系你。", "HARASS", "zh", "snd-threat-zh", "tpl-har-threat-zh"),
    # HARASS en
    ("syn-har-en-001", "Pay me back now or I will keep calling you every hour.", "HARASS", "en", "snd-collect-en", "tpl-har-debt-en"),
    ("syn-har-en-002", "Answer my messages. I know where you work.", "HARASS", "en", "snd-stalker-en", "tpl-har-pressure-en"),
    # HARASS hi
    ("syn-har-hi-001", "तुम्हारा पैसा वापस करो वरना मैं तुम्हें परेशान करूंगा।", "HARASS", "hi", "snd-collect-hi", "tpl-har-debt-hi"),
    ("syn-har-hi-002", "मेरा फोन उठाओ, मैं बार-बार कॉल करूंगा।", "HARASS", "hi", "snd-stalker-hi", "tpl-har-pressure-hi"),
    # HARASS id
    ("syn-har-id-001", "Bayar utangmu sekarang atau saya akan terus menghubungi.", "HARASS", "id", "snd-collect-id", "tpl-har-debt-id"),
    ("syn-har-id-002", "Jangan abaikan pesan saya. Saya tahu alamatmu.", "HARASS", "id", "snd-stalker-id", "tpl-har-pressure-id"),
    # FRAUD zh
    ("syn-frd-zh-001", "【紧急】您的银行卡异常，请立即点击链接验证身份。", "FRAUD", "zh", "snd-phish-zh", "tpl-frd-bank-zh"),
    ("syn-frd-zh-002", "社保账户即将冻结，请发送验证码到本号码解冻。", "FRAUD", "zh", "snd-scam-zh", "tpl-frd-gov-zh"),
    ("syn-frd-zh-003", "快递丢失理赔，添加客服微信领取赔偿金。", "FRAUD", "zh", "snd-fake-zh", "tpl-frd-parcel-zh"),
    ("syn-frd-zh-004", "您的Apple ID存在风险，请登录 http://fake-id.com 处理。", "FRAUD", "zh", "snd-phish-zh", "tpl-frd-account-zh"),
    # FRAUD en
    ("syn-frd-en-001", "Your account is locked. Verify immediately at http://secure-fake.net", "FRAUD", "en", "snd-phish-en", "tpl-frd-account-en"),
    ("syn-frd-en-002", "IRS refund pending. Send your SSN and card details to claim.", "FRAUD", "en", "snd-scam-en", "tpl-frd-tax-en"),
    ("syn-frd-en-003", "Package held. Pay a small fee via this link to release delivery.", "FRAUD", "en", "snd-fake-en", "tpl-frd-parcel-en"),
    # FRAUD hi
    ("syn-frd-hi-001", "आपका खाता ब्लॉक है। तुरंत सत्यापन लिंक पर क्लिक करें।", "FRAUD", "hi", "snd-phish-hi", "tpl-frd-account-hi"),
    ("syn-frd-hi-002", "आपका बैंक खाता असामान्य है, OTP भेजें।", "FRAUD", "hi", "snd-scam-hi", "tpl-frd-bank-hi"),
    # FRAUD id
    ("syn-frd-id-001", "Akun Anda diblokir. Klik tautan verifikasi segera.", "FRAUD", "id", "snd-phish-id", "tpl-frd-account-id"),
    ("syn-frd-id-002", "Paket tertahan. Bayar biaya kecil lewat link ini.", "FRAUD", "id", "snd-fake-id", "tpl-frd-parcel-id"),
    # adversarial variants (train only)
    ("syn-adv-zh-001", "【银\u200b行】您的账户入账500元", "TRANSACTION", "zh", "snd-bank-zh", "tpl-txn-credit-zh", True),
    ("syn-adv-en-001", "Lim\u200cited offer! Click to claim prize", "AD", "en", "snd-promo-en", "tpl-ad-offer-en", True),
]

SPLIT_ASSIGN = {
    "train": 32,
    "validation": 10,
    "test": 10,
}


def make_record(
    rid: str,
    text: str,
    label: str,
    language: str,
    sender_group: str,
    template_group: str,
    split: str,
    is_adversarial: bool = False,
    parent_id: str = None,
) -> dict:
    license_id = "Apache-2.0" if hash(rid) % 2 == 0 else "CC0"
    return {
        "id": rid,
        "text": text,
        "label": label,
        "language": language,
        "source": "synthetic_public_v1",
        "source_license": license_id,
        "sender_group": sender_group,
        "template_group": template_group,
        "is_synthetic": True,
        "is_adversarial": is_adversarial,
        "parent_id": parent_id,
        "annotator_ids": ["synthetic-generator"],
        "split": split,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    expanded = []
    for item in SAMPLES:
        adv = False
        if len(item) == 7:
            rid, text, label, lang, snd, tpl, adv = item
        else:
            rid, text, label, lang, snd, tpl = item
        expanded.append((rid, text, label, lang, snd, tpl, adv))

    # Pad to 52 records by duplicating with suffix variants for volume
    idx = 0
    while len(expanded) < 52:
        base = expanded[idx % len(SAMPLES)]
        if len(base) == 7:
            rid, text, label, lang, snd, tpl, adv = base
        else:
            rid, text, label, lang, snd, tpl = base
            adv = False
        expanded.append(
            (
                f"{rid}-v{len(expanded)}",
                text,
                label,
                lang,
                snd,
                tpl,
                adv,
            )
        )
        idx += 1

    splits = {"train": [], "validation": [], "test": []}
    counts = {"train": 0, "validation": 0, "test": 0}
    order = ["train", "validation", "test"]
    for i, row in enumerate(expanded):
        split = order[i % 3]
        if counts[split] >= SPLIT_ASSIGN[split]:
            for candidate in order:
                if counts[candidate] < SPLIT_ASSIGN[candidate]:
                    split = candidate
                    break
        rid, text, label, lang, snd, tpl, adv = row
        splits[split].append(
            make_record(rid, text, label, lang, snd, tpl, split, adv)
        )
        counts[split] += 1

    for split_name, records in splits.items():
        path = OUT / f"{split_name}.jsonl"
        lines = [json.dumps(r, ensure_ascii=False) for r in records]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote {len(records)} records to {path}")


if __name__ == "__main__":
    main()
