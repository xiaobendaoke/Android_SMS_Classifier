import csv
import re
import sys

INPUT_FILE = r"C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier\training\data\interim\annotation\chunks\chunk_02.csv"

# Patterns for classification
FRAUD_PATTERNS = [
    r'won.*\b(cash|prize|award|money)\b',
    r'\b(call|text).*\d{5,}.*(claim|won|prize|award)',
    r'prize.*(claim|uncollected|unredeemed)',
    r'(un-redeemed|unredeemed)\b.*(points|credit|SIM|S\.I\.M)',
    r'congratulations.*won',
    r'(guaranteed|cash|award).*call',
    r'selected.*(receive|award|prize)',
    r'urgent.*(call|won|prize|award)',
    r'complimentary.*call',
    r'(Ibiza|holiday|cash).*(await|collection|claim)',
    r'secret admirer.*call',
    r'REVEAL.*stop',
    r'(prescripiton|drvgs?|pharmacy)',
    r'customer service announcement.*premier',
    r'discount voucher.*text.*\d{5}',
    r'(PO Box|POBox).*\d{5,}.*(ppm|150)',
    r'(SavaMob|expressoffer|TXTAUCTION|cnupdates|getzed|ldew|smsco|comuk)',
    r'(posh birds|user trial|champneys)',
]

AD_PATTERNS = [
    r'ringtone',
    r'(half price|new).*(camera phone|mobile|rental)',
    r'line rental',
    r'(mobiles|mobile content).*(free|direct)',
    r'(Nokia|Orange).*(tone|rental|upgrade)',
    r'(polyphonic|poly).*(tone)',
    r'txt.*(tone|music|sub).*\d{5}',
    r'stop.*800\d+',
    r'(video phone|camcorder).*free',
    r'(free).*(minute|text|nokia|tone|camera|roses)',
    r'(rental|upgrade).*call',
    r'(join|text).*mobile community',
    r'(text dating|gaytextbuddy|dating service)',
    r'(text VIP|VIP to 83)',
    r'(zed\s0870|1417012)',
    r'(anytime any network|any network mins)',  # mobile plan ads
    r'(outbid.*|bid again|auction)',  # auction ads
    r'(Paris|flight|holiday).*(Book now|call)',  # travel ads
]

HARASS_PATTERNS = [
    r'(horny|lapdancer|sex|live.*bedroom|text SUE|bedroom now)',
    r'(massage.*baby oil|fave position)',
    r'(inner tigress)',
    r'chikku.*msg',
    r'Kama sutra',
]


def classify_sms(text, uci_binary):
    text_lower = text.lower()

    for pat in FRAUD_PATTERNS:
        if re.search(pat, text_lower):
            return "FRAUD", detect_fraud_reason(text)

    for pat in HARASS_PATTERNS:
        if re.search(pat, text_lower):
            return "HARASS", detect_harass_reason(text)

    for pat in AD_PATTERNS:
        if re.search(pat, text_lower):
            return "AD", detect_ad_reason(text)

    if uci_binary == "spam":
        if re.search(r'\bfree\b.*\b(call|reply|text|tone|week|entry)', text_lower):
            return "AD", "含免费优惠/订阅等营销内容"
        if re.search(r'\b(text|txt)\b.*\b\d{5}\b', text_lower):
            return "AD", "通过短信订阅付费服务"
        if re.search(r'\bstop\b.*\b\d{5,}\b', text_lower):
            return "AD", "含退订指令的营销短信"
        if re.search(r'(won|won|prize|cash|award|congrat)', text_lower):
            return "FRAUD", "虚假中奖/奖品骗取联系"
        if re.search(r'(urgent|important)', text_lower) and re.search(r'\b\d{5,}\b', text_lower):
            return "FRAUD", "伪造紧急通知引导拨打"
        if re.search(r"http\b.*moby|http.*download|collect.*content", text_lower):
            return "FRAUD", "虚假内容下载链接骗取点击"
        return "NEEDS_REVIEW", "spam但无法明确归入TRANSACTION/AD/HARASS/FRAUD"

    return "NEEDS_REVIEW", "私人闲聊/个人对话"


def detect_fraud_reason(text):
    t = text.lower()
    if re.search(r'(un-redeemed|unredeemed)\b.*(S\.I\.M|SIM|points|credit)', t):
        return "伪造积分余额骗取个人信息"
    if re.search(r'(prescripiton|drvgs?)', t):
        return "假药/处方广告骗取购买"
    if re.search(r'(Ibiza|holiday|cash).*(await|collection|complimentary)', t):
        return "虚假假期/现金奖励骗取联系"
    if re.search(r'(secret admirer|REVEAL)', t):
        return "虚假暗恋揭秘骗取拨打电话"
    if re.search(r'(posh birds|user trial|champneys)', t):
        return "虚假市场调研骗取个人信息"
    if re.search(r'(customer.*service.*announcement|premier)', t):
        return "冒充客服虚假通知"
    if re.search(r'(SavaMob|discount voucher|expressoffer)', t):
        return "虚假优惠券骗取回复"
    if re.search(r'(won|cash|prize|award|guaranteed)', t):
        return "虚假中奖骗取拨打高费率电话"
    if re.search(r'(urgent|message waiting)', t):
        return "伪造紧急消息骗取回拨"
    if re.search(r'text (YES|SHOP|MUSIC|TONE|START|STORE) to', t):
        return "付费订阅/虚假优惠骗取回复"
    if re.search(r'http.*(moby|download)', t):
        return "虚假下载链接骗取点击"
    return "虚假信息或钓鱼骗取用户操作"


def detect_ad_reason(text):
    t = text.lower()
    if re.search(r'ringtone|polyphonic|tone.*wk', t):
        return "铃声/彩铃订阅收费广告"
    if re.search(r'(camera phone|mobile|rental|upgrade).*(free|half price)', t):
        return "手机/设备租赁促销广告"
    if re.search(r'(video phone|camcorder)', t):
        return "视频手机换取广告"
    if re.search(r'(join|text).*mobile community|dating|VIP.*83', t):
        return "交友/约会付费服务推广"
    if re.search(r'(Nokia|Orange|Tone).*txt', t):
        return "品牌促销/短信订阅服务"
    if re.search(r'(zed|charity)', t):
        return "慈善/铃声营销"
    if re.search(r'(outbid|auction|bid)', t):
        return "拍卖平台推广"
    if re.search(r'(Paris|flight|holiday|book now)', t):
        return "旅游度假促销广告"
    if re.search(r'(anytime|any network mins|mins.*text.*phone)', t):
        return "移动套餐促销广告"
    if re.search(r'(roses|free.*event|club)', t):
        return "活动/俱乐部推广"
    return "正规商家促销/订阅广告"


def detect_harass_reason(text):
    t = text.lower()
    if re.search(r'(lapdancer|sex|text SUE|bedroom|horny)', t):
        return "成人/色情骚扰短信"
    if re.search(r'(massage|baby oil|kama sutra|fave position)', t):
        return "性暗示骚扰内容"
    if re.search(r'inner tigress', t):
        return "性暗示骚扰内容"
    return "灰色交友/骚扰内容"


def main():
    rows = []
    with open(INPUT_FILE, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)

    counts = {"TRANSACTION": 0, "AD": 0, "HARASS": 0, "FRAUD": 0, "NEEDS_REVIEW": 0}

    for row in rows:
        label, notes = classify_sms(row['text'], row['uci_binary'])
        row['label'] = label
        row['notes'] = notes
        counts[label] += 1

    with open(INPUT_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"处理完成！共 {len(rows)} 条记录")
    print(f"  FRAUD:        {counts['FRAUD']}")
    print(f"  TRANSACTION:  {counts['TRANSACTION']}")
    print(f"  AD:           {counts['AD']}")
    print(f"  HARASS:       {counts['HARASS']}")
    print(f"  NEEDS_REVIEW: {counts['NEEDS_REVIEW']}")


if __name__ == '__main__':
    main()
