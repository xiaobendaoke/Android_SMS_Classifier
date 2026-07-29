# -*- coding: utf-8 -*-
"""Review AD-labeled ZH SMS and emit _fix_ad.json relabel list."""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

SRC = Path(__file__).with_name("zh_all_suggested.csv")
OUT = Path(__file__).with_name("_fix_ad.json")

MOBILE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
FW_DIGIT = str.maketrans("０１２３４５６７８９　", "0123456789 ")


def normalize(text: str) -> str:
    """Fullwidth digits + strip spaces/slashes for keyword matching."""
    t = (text or "").translate(FW_DIGIT)
    return re.sub(r"[\s/]+", "", t)


BANK_OFFICIAL = (
    "邮储银行",
    "平安银行",
    "兴业银行",
    "招商银行",
    "中国银行",
    "工商银行",
    "建设银行",
    "农业银行",
    "交通银行",
    "中信银行",
    "光大银行",
    "民生银行",
    "浦发银行",
    "华夏银行",
    "广发银行",
    "【平安银行】",
    "【招商银行】",
    "【中国银行】",
)
CARRIER = (
    "中国移动",
    "中国联通",
    "中国电信",
    "杭州移动",
    "【移动】",
    "【联通】",
    "【电信】",
)
LEGIT_BRAND = (
    "【天猫】",
    "【京东】",
    "【大众点评】",
    "【小米】",
    "【红牛",
    "世纪佳缘",
    "无线城市",
)


def has_any(t: str, keys) -> bool:
    return any(k in t for k in keys)


def is_property_or_auto_loan_mention(t: str) -> bool:
    """房产/购车广告里顺带提贷款 → 仍是 AD，不改 HARASS。"""
    return has_any(
        t,
        (
            "可正常贷款",
            "可贷款",
            "不限购",
            "淘宝贷款",
            "天猫贷款",
            "购车",
            "楼盘",
            "别墅",
            "公寓",
            "商铺",
            "售楼",
            "永久产权",
            "首付",
            "看房",
            "现房",
            "房产投资",
            "澳洲房产",
            "新加坡",
        ),
    )


def is_official_bank_product_ad(t: str) -> bool:
    """正规银行明确贷款/办卡产品促销 → 保留 AD。"""
    if not has_any(t, BANK_OFFICIAL):
        return False
    if has_any(t, ("新一贷", "随兴贷", "邮储银行", "信用卡", "办卡")):
        return True
    # 分行/支行产品介绍且无“无抵押当天放款”私人中介话术
    if has_any(t, ("房产抵押", "消费贷款", "授信")) and not has_any(
        t, ("当天放款", "当天下款", "无抵押", "免担保", "下款快")
    ):
        return True
    return False


def classify(text: str):
    t = (text or "").strip()
    n = normalize(t)
    if not t:
        return "NEEDS_REVIEW", "空文本无法判断"

    # ========== ① FRAUD ==========
    if has_any(
        n,
        (
            "安全账户",
            "账户异常",
            "洗钱",
            "提供密码",
            "告知验证码",
            "把验证码",
            "转账到安全",
        ),
    ):
        if "法院对面" not in t:
            return "FRAUD", "钓鱼/冒充或索要验证码密码"
    if "涉嫌" in t and has_any(t, ("公安", "检察院", "法院传", "刑事")):
        return "FRAUD", "假公检法恐吓话术"

    fake_prize = has_any(
        n,
        (
            "恭喜您中奖",
            "您已中奖",
            "中奖通知",
            "领取奖金",
            "立即兑奖",
            "点击领奖",
            "免费领取iPhone",
            "0元领iPhone",
            "中大奖",
        ),
    )
    if fake_prize and not has_any(
        t, ("双色球", "不保证中奖", "大众点评", "红牛", "中福在线") + LEGIT_BRAND + CARRIER + BANK_OFFICIAL
    ):
        return "FRAUD", "假中奖/诱导领奖"

    if has_any(n, ("领奖", "兑奖")) and re.search(
        r"https?://|wap\.|\w+\.(cn|com)/\w+", t, re.I
    ):
        if not has_any(t, LEGIT_BRAND + CARRIER + BANK_OFFICIAL + ("中福在线", "红牛", "无线城市", "中国移动", "139邮箱")):
            return "FRAUD", "不明短链领奖诱导"

    # ========== ② TRANSACTION ==========
    t_digits = t.translate(FW_DIGIT)
    if re.search(r"您账户\d+于.*(扣款|入账|消费|支出|存入)", t_digits):
        return "TRANSACTION", "账户扣款/入账等业务结果告知（主意图）"
    if re.search(r"(验证码是|验证码为|动态码|校验码是|短信验证码)[：:\s]*\d{4,8}", t_digits):
        if not has_any(t, ("转发验证码", "告诉别人", "提供给")):
            return "TRANSACTION", "纯验证码事务短信"
    if has_any(n, ("取件码", "快递已到达", "已到达驿站", "待取件", "丰巢")) and not has_any(
        t, ("优惠", "促销", "办卡", "充值送")
    ):
        return "TRANSACTION", "物流取件事务告知"

    # ========== ④ HARASS（跳过③AD：本脚本只审 AD 错标）==========
    if ("代开" in n and "发票" in n) or has_any(
        n, ("代开发票", "发票代开", "发票均可代开", "有发票可向外代开")
    ):
        return "HARASS", "代开发票灰产招揽"

    if has_any(
        n,
        (
            "莞式",
            "包夜",
            "特殊服务",
            "出台服务",
            "技师上门",
            "裸聊",
            "一夜情",
            "全套上门",
        ),
    ):
        return "HARASS", "成人/色情服务招揽"

    if has_any(
        n,
        (
            "娱乐城",
            "百家乐",
            "六合彩",
            "时时彩",
            "真人荷官",
            "开户即送",
            "送彩金",
            "扎金花",
            "澳门赌场",
        ),
    ):
        return "HARASS", "赌博/博彩招揽"

    if "双色球" in n and "专家推荐" in n and has_any(n, ("投注", "自选回")):
        return "HARASS", "彩票投注招揽（专家荐号诱导投注）"

    if has_any(
        n,
        (
            "带学员",
            "带客买入",
            "带客建",
            "锁仓金股",
            "明日必涨",
            "内线",
            "冲高出货",
            "尾盘买入",
        ),
    ) or (
        has_any(n, ("私募基金", "私募"))
        and has_any(n, ("必涨", "带学员", "金股", "拉停", "建仓"))
    ):
        return "HARASS", "荐股带客灰产硬推销"

    if has_any(n, ("合作前期无费用", "前期无费用", "诚寻好项目")) and has_any(
        n, ("资金", "合作")
    ):
        return "HARASS", "资金中介/灰产合作招揽"

    # 代办学历/驾驶证等灰产
    if has_any(n, ("代办证", "假证", "办假证", "真实驾驶证", "代办各院校")) or (
        "代办" in n and has_any(n, ("发票", "营业执照", "资格证", "驾驶证", "大专", "大本"))
    ):
        return "HARASS", "代办证件/学历灰产"

    loan_hard = has_any(
        n,
        (
            "无抵押",
            "免担保",
            "当天放款",
            "当天下款",
            "3天放款",
            "日放款",
            "下款快",
            "放款快",
            "小额贷款",
            "信用贷",
            "信用贷款",
            "抵押贷款",
            "二次贷款",
            "装修贷款",
            "大额无抵",
            "信用岱歀",
        ),
    )
    if loan_hard and not is_property_or_auto_loan_mention(t):
        if not is_official_bank_product_ad(t):
            phone = MOBILE.search(n)
            if has_any(
                n,
                (
                    "无抵押",
                    "免担保",
                    "当天放款",
                    "当天下款",
                    "小额贷款",
                    "下款快",
                    "放款快",
                    "3天放款",
                    "日放款",
                    "信用岱歀",
                    "链家金融",
                ),
            ) or (
                phone is not None
                and has_any(n, ("贷款", "放款", "下款", "抵押", "信用贷"))
            ):
                return "HARASS", "无抵押/当天放款/私人中介硬推销贷款"

    # ========== ⑤ NEEDS_REVIEW ==========
    if "冲浪助手" in t:
        return "NEEDS_REVIEW", "纯新闻/资讯推送（冲浪助手）"
    if has_any(t, ("飞信好友", "【发自飞信】", "希望加您为飞信")):
        return "NEEDS_REVIEW", "私人飞信/闲聊非目标域"
    if has_any(t, ("财富早间版", "财富收盘版", "财富版：")) and has_any(
        t, ("投资建议", "仅供参考", "仓位", "指数", "股指", "减仓", "逢高")
    ):
        return "NEEDS_REVIEW", "券商投研/行情推送非四类目标域"
    if "投资建议仅供参考" in t and has_any(t, ("财富", "收盘", "早间")):
        return "NEEDS_REVIEW", "券商投研推送非四类目标域"
    if t in ("2.最新活动", "VIP6 贵宾客户-专享活动特权") or re.fullmatch(
        r"\[手机电话\]:\s*\+?\d+", t
    ):
        return "NEEDS_REVIEW", "信息碎片无法判断"
    if len(t) <= 6 and not has_any(t, ("优惠", "验证码", "中奖")):
        return "NEEDS_REVIEW", "过短无法判断"

    return None, None


def main() -> int:
    with SRC.open(encoding="gbk", errors="replace", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("label") or "").strip() == "AD"]

    changes = []
    for r in rows:
        new_lab, reason = classify(r.get("text") or "")
        if new_lab:
            changes.append(
                {"id": r["id"], "old": "AD", "new": new_lab, "reason": reason}
            )

    seen = set()
    uniq = []
    for c in changes:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        uniq.append(c)
    order = {"FRAUD": 0, "TRANSACTION": 1, "HARASS": 2, "NEEDS_REVIEW": 3}
    uniq.sort(key=lambda x: (order.get(x["new"], 9), x["id"]))

    out = {"changes": uniq, "reviewed": len(rows)}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    cnt = Counter(c["new"] for c in uniq)
    print("reviewed", len(rows))
    print("changes", len(uniq))
    print("by new:", dict(cnt))
    print("written", OUT)

    id2t = {r["id"]: r["text"] for r in rows}
    for lab in ["FRAUD", "TRANSACTION", "HARASS", "NEEDS_REVIEW"]:
        subset = [c for c in uniq if c["new"] == lab]
        print(f"\n---- {lab} ({len(subset)}) ----")
        for c in subset[:15]:
            print(c["id"], c["reason"], "|", (id2t.get(c["id"]) or "")[:90])
        if len(subset) > 15:
            print("...")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
